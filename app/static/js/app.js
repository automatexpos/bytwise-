/*
 * Vanilla JS for Bytwise: Leaflet map init (mirrors Map.tsx's
 * OpenStreetMap tile layer and custom marker pin), toast show/hide
 * (mirrors ToastContext.tsx/Toast.tsx), AJAX calls to the JSON endpoints
 * in app/routers/api.py, and client side form validation.
 *
 * No build step, no framework, just plain DOM APIs and fetch.
 */

/* ==================== TOASTS ==================== */

function showToast(message, type) {
    type = type || "info";
    var container = document.getElementById("toast-container");
    if (!container) return;

    var icons = { success: "fa-check-circle", error: "fa-exclamation-circle", info: "fa-info-circle" };
    var toast = document.createElement("div");
    toast.className = "toast toast-" + type;
    toast.innerHTML =
        '<i class="fas ' + (icons[type] || icons.info) + '"></i>' +
        '<p>' + escapeHtml(message) + "</p>" +
        '<button type="button" class="toast-close" aria-label="Dismiss"><i class="fas fa-times"></i></button>';

    container.appendChild(toast);

    var remove = function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    };
    toast.querySelector(".toast-close").addEventListener("click", remove);
    setTimeout(remove, 3000);
}

function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

var toast = {
    success: function (msg) { showToast(msg, "success"); },
    error: function (msg) { showToast(msg, "error"); },
    info: function (msg) { showToast(msg, "info"); },
};

/* ==================== FETCH HELPER ==================== */

function postJson(url, payload) {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
    }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
            if (!response.ok) {
                var message = (data && data.detail) || "Something went wrong.";
                throw new Error(message);
            }
            return data;
        });
    });
}

/* ==================== MAP & HOME FILTERING ==================== */

var _map = null;
var _markers = [];
var _currentShops = [];
var _userLocation = null;
var _userLocationMarker = null;
var _radiusCircle = null;
var _activeRadiusKm = null;

function updateUserLocationMarker(lat, lng) {
    if (!_map || typeof L === "undefined") return;
    if (_userLocationMarker) {
        _userLocationMarker.setLatLng([lat, lng]);
    } else {
        _userLocationMarker = L.circleMarker([lat, lng], {
            radius: 8,
            fillColor: "#3b82f6",
            color: "#ffffff",
            weight: 2,
            opacity: 1,
            fillOpacity: 1,
        }).addTo(_map);
        _userLocationMarker.bindTooltip("You are here", { permanent: false, direction: "top" });
    }
}

function updateRadiusCircle() {
    if (!_map || typeof L === "undefined") return;

    if (_activeRadiusKm && _activeRadiusKm > 0 && _userLocation) {
        var radiusMeters = _activeRadiusKm * 1000;
        if (_radiusCircle) {
            _radiusCircle.setLatLng([_userLocation.lat, _userLocation.lng]);
            _radiusCircle.setRadius(radiusMeters);
        } else {
            _radiusCircle = L.circle([_userLocation.lat, _userLocation.lng], {
                radius: radiusMeters,
                color: "#F08000",
                fillColor: "#F08000",
                fillOpacity: 0.12,
                weight: 2,
                dashArray: "6, 6",
            }).addTo(_map);
        }
        try {
            _map.fitBounds(_radiusCircle.getBounds(), { padding: [35, 35], maxZoom: 15 });
        } catch (e) {}
    } else {
        if (_radiusCircle) {
            _radiusCircle.remove();
            _radiusCircle = null;
        }
    }
}

function requestUserLocation(callback, centerView) {
    var locateBtn = document.getElementById("locate-me-btn");
    if (locateBtn) {
        locateBtn.disabled = true;
        locateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    if (!navigator.geolocation && (!_map || typeof L === "undefined")) {
        if (locateBtn) {
            locateBtn.disabled = false;
            locateBtn.innerHTML = '<i class="fas fa-location-arrow"></i>';
        }
        toast.error("Geolocation is not supported by your browser.");
        if (callback) callback(false);
        return;
    }

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            function (position) {
                if (locateBtn) {
                    locateBtn.disabled = false;
                    locateBtn.innerHTML = '<i class="fas fa-location-arrow"></i>';
                }
                var lat = position.coords.latitude;
                var lng = position.coords.longitude;
                _userLocation = { lat: lat, lng: lng };

                var latInput = document.getElementById("user-lat-input");
                var lngInput = document.getElementById("user-lng-input");
                if (latInput) latInput.value = lat;
                if (lngInput) lngInput.value = lng;

                updateUserLocationMarker(lat, lng);
                if (_map && centerView) {
                    _map.setView([lat, lng], 14);
                }
                if (callback) callback(true);
            },
            function (error) {
                if (locateBtn) {
                    locateBtn.disabled = false;
                    locateBtn.innerHTML = '<i class="fas fa-location-arrow"></i>';
                }
                toast.error("Could not access your location. Please check browser permissions.");
                if (callback) callback(false);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
    } else {
        _map.locate({ setView: !!centerView, maxZoom: 14 });
        _map.once("locationfound", function (e) {
            if (locateBtn) {
                locateBtn.disabled = false;
                locateBtn.innerHTML = '<i class="fas fa-location-arrow"></i>';
            }
            _userLocation = { lat: e.latlng.lat, lng: e.latlng.lng };
            var latInput = document.getElementById("user-lat-input");
            var lngInput = document.getElementById("user-lng-input");
            if (latInput) latInput.value = e.latlng.lat;
            if (lngInput) lngInput.value = e.latlng.lng;

            updateUserLocationMarker(e.latlng.lat, e.latlng.lng);
            if (callback) callback(true);
        });
        _map.once("locationerror", function () {
            if (locateBtn) {
                locateBtn.disabled = false;
                locateBtn.innerHTML = '<i class="fas fa-location-arrow"></i>';
            }
            toast.error("Could not access your location.");
            if (callback) callback(false);
        });
    }
}

function handleRadiusChange(selectElem) {
    var radiusVal = selectElem.value;
    var form = document.getElementById("home-filter-form");
    if (!form) return;

    if (!radiusVal) {
        form.submit();
        return;
    }

    var latInput = document.getElementById("user-lat-input");
    var lngInput = document.getElementById("user-lng-input");

    if (latInput && lngInput && latInput.value && lngInput.value) {
        form.submit();
    } else {
        toast.info("Acquiring your location for radius calculation...");
        requestUserLocation(function (success) {
            if (success) {
                form.submit();
            } else {
                selectElem.value = "";
            }
        }, false);
    }
}

function initShopsMap(containerId, shops, options) {
    var container = document.getElementById(containerId);
    if (!container || typeof L === "undefined") return;

    options = options || {};
    _currentShops = shops || [];

    _map = L.map(containerId, { zoomControl: false, attributionControl: false }).setView([39.8283, -98.5795], 4);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
    }).addTo(_map);

    L.control.zoom({ position: "bottomright" }).addTo(_map);

    var resizeObserver = new ResizeObserver(function () {
        _map.invalidateSize();
    });
    resizeObserver.observe(container);

    if (options.userLat && options.userLng) {
        var lat = parseFloat(options.userLat);
        var lng = parseFloat(options.userLng);
        if (!isNaN(lat) && !isNaN(lng)) {
            _userLocation = { lat: lat, lng: lng };
            updateUserLocationMarker(lat, lng);
        }
    }

    if (options.radius) {
        _activeRadiusKm = parseFloat(options.radius);
    }

    // If user location not set yet, silently request it to pre-fill for radius queries
    if (!_userLocation && navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function (pos) {
            _userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
            var latInput = document.getElementById("user-lat-input");
            var lngInput = document.getElementById("user-lng-input");
            if (latInput) latInput.value = pos.coords.latitude;
            if (lngInput) lngInput.value = pos.coords.longitude;
            updateUserLocationMarker(pos.coords.latitude, pos.coords.longitude);
            if (_activeRadiusKm && _activeRadiusKm > 0) {
                updateRadiusCircle();
            }
        }, function () {}, { timeout: 8000, maximumAge: 300000 });
    }

    renderShopMarkers(_currentShops || []);

    if (_activeRadiusKm && _userLocation) {
        updateRadiusCircle();
    }

    // Set up Locate Me button
    var locateBtn = document.getElementById("locate-me-btn");
    if (locateBtn) {
        locateBtn.addEventListener("click", function () {
            requestUserLocation(function (success) {
                if (success && _activeRadiusKm && _activeRadiusKm > 0) {
                    var form = document.getElementById("home-filter-form");
                    if (form) form.submit();
                }
            }, true);
        });
    }

    // Filter change listeners
    var cityFilter = document.getElementById("city-filter");
    if (cityFilter) {
        cityFilter.addEventListener("change", function () {
            this.form.submit();
        });
    }

    var ratingFilter = document.getElementById("rating-filter");
    if (ratingFilter) {
        ratingFilter.addEventListener("change", function () {
            this.form.submit();
        });
    }

    var radiusFilter = document.getElementById("radius-filter");
    if (radiusFilter) {
        radiusFilter.addEventListener("change", function () {
            handleRadiusChange(this);
        });
    }

    document.querySelectorAll('.home-search-form input[name="vibe"]').forEach(function (checkbox) {
        checkbox.addEventListener("change", function () {
            this.form.submit();
        });
    });

    var mapSearchInput = document.getElementById("map-search-input");
    if (mapSearchInput) {
        mapSearchInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                var searchInput = document.getElementById("search-input");
                if (searchInput) searchInput.value = mapSearchInput.value;
                var form = document.getElementById("home-filter-form");
                if (form) form.submit();
            }
        });
    }
}

function renderShopMarkers(shops) {
    if (!_map || typeof L === "undefined") return;

    _markers.forEach(function (marker) { marker.remove(); });
    _markers = [];

    var markerGroup = L.featureGroup();

    shops.forEach(function (shop) {
        if (!shop.location) return;
        var lat = parseFloat(shop.location.lat);
        var lng = parseFloat(shop.location.lng);
        if (isNaN(lat) || isNaN(lng) || (lat === 0 && lng === 0)) return;

        var ratingText = shop.peopleSayRating ? Number(shop.peopleSayRating).toFixed(1) : "New";
        var customIcon = L.divIcon({
            className: "custom-div-icon",
            html:
                "<div class='custom-marker-wrap'>" +
                "<div class='custom-marker-label'>" +
                "<span class='custom-marker-name'>" + escapeHtml(shop.name) + "</span>" +
                "<span class='custom-marker-rating'><i class='fas fa-star'></i> " + ratingText + "</span>" +
                "</div>" +
                "<div class='custom-marker-pin'></div>" +
                "</div>",
            iconSize: [160, 66],
            iconAnchor: [80, 42],
        });

        var marker = L.marker([lat, lng], { icon: customIcon }).addTo(_map);
        marker.on("click", function () {
            window.location.href = "/shop/" + shop.id;
        });

        var imageUrl = (shop.gallery && shop.gallery[0] && shop.gallery[0].url) || "";
        var address = shop.location.address || "";
        var mapsUrl = address.indexOf("http") === 0
            ? address
            : "https://www.google.com/maps/search/?api=1&query=" +
              encodeURIComponent(shop.name + ", " + address + ", " + shop.location.city);

        var distanceHtml = "";
        if (shop.distance != null && !isNaN(shop.distance)) {
            distanceHtml = '<p style="margin:0 0 0.4rem;font-size:0.75rem;font-weight:700;color:#F08000;"><i class="fas fa-location-dot"></i> ' + shop.distance + ' km away</p>';
        }

        var popupContent =
            '<div>' +
            '<div style="height:96px;width:100%;overflow:hidden;background:#eee;">' +
            '<img src="' + imageUrl + '" style="width:100%;height:100%;object-fit:cover;">' +
            "</div>" +
            '<div style="padding:0.75rem;">' +
            '<h3 style="margin:0 0 0.25rem;font-weight:700;">' + escapeHtml(shop.name) + "</h3>" +
            '<p style="margin:0 0 0.35rem;font-size:0.8rem;color:#8a7666;">' + escapeHtml(shop.location.city) + "</p>" +
            distanceHtml +
            '<a href="' + mapsUrl + '" target="_blank" rel="noreferrer" ' +
            'style="font-size:0.75rem;font-weight:700;background:#F08000;color:#fff;padding:0.4rem 0.7rem;border-radius:8px;display:inline-block;">' +
            '<i class="fas fa-location-dot"></i> Location</a>' +
            "</div>" +
            "</div>";

        marker.bindPopup(popupContent);
        _markers.push(marker);
        markerGroup.addLayer(marker);
    });

    if (!_radiusCircle && shops.length > 0) {
        try {
            var bounds = markerGroup.getBounds();
            if (bounds.isValid()) {
                _map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
            }
        } catch (e) {
            /* no-op */
        }
    }
}

/* ==================== HOME: MOBILE VIEW TOGGLE ==================== */

function setHomeView(mode) {
    var sidebar = document.getElementById("home-sidebar");
    var mapSection = document.getElementById("home-map-section");
    if (!sidebar || !mapSection) return;

    document.querySelectorAll(".view-toggle-btn").forEach(function (btn) {
        btn.classList.toggle("active", btn.getAttribute("data-view") === mode);
    });

    if (mode === "map") {
        sidebar.classList.add("hidden-mobile");
        mapSection.classList.remove("hidden-mobile");
        if (_map) setTimeout(function () { _map.invalidateSize(); }, 50);
    } else {
        sidebar.classList.remove("hidden-mobile");
        mapSection.classList.add("hidden-mobile");
    }
}

/* ==================== SAVE / VISIT / VOTE / FOLLOW ==================== */

function toggleSaveShop(shopId, button) {
    postJson("/api/save-shop", { shopId: shopId })
        .then(function (data) {
            var icon = button.querySelector("i");
            var label = button.querySelector("span");
            if (data.saved) {
                button.classList.remove("btn-outline");
                button.classList.add("btn-secondary");
                if (icon) icon.className = "fas fa-heart";
                if (label) label.textContent = "Saved";
                toast.success("Added to your saved spots!");
            } else {
                button.classList.remove("btn-secondary");
                button.classList.add("btn-outline");
                if (icon) icon.className = "far fa-heart";
                if (label) label.textContent = "Save Spot";
            }
        })
        .catch(function (error) { toast.error(error.message); });
}

function handleVisitedClick(shopId, isClaimedOwner) {
    if (isClaimedOwner) {
        toast.error("Owners cannot review or stamp their own spot.");
        return;
    }
    var button = document.getElementById("visit-shop-btn");
    var isVisited = button && button.getAttribute("data-visited") === "true";
    markVisited(shopId, !isVisited);
}

function markVisited(shopId, visited, rating, comment) {
    var payload = { shopId: shopId };
    if (rating) payload.rating = rating;
    if (comment) payload.comment = comment;

    var button = document.getElementById("visit-shop-btn");
    if (button) button.disabled = true;

    return postJson("/api/visit-shop", payload).then(function (data) {
        if (button) {
            button.disabled = false;
            button.setAttribute("data-visited", data.visited ? "true" : "false");
            var icon = button.querySelector("i");
            var label = button.querySelector("span");
            if (data.visited) {
                button.classList.remove("btn-outline");
                button.classList.add("btn-secondary");
                if (icon) icon.className = "fas fa-check-circle";
                if (label) label.textContent = "Visited";
                toast.success("Passport Stamped!");
            } else {
                button.classList.remove("btn-secondary");
                button.classList.add("btn-outline");
                if (icon) icon.className = "fas fa-stamp";
                if (label) label.textContent = "Stamp My Passport";
                toast.info("Passport stamp removed.");
            }
        }
        return data;
    }).catch(function (err) {
        if (button) button.disabled = false;
        toast.error(err.message || "Failed to update passport stamp.");
    });
}

var _reviewRating = 5;

function openReviewModal() {
    var modal = document.getElementById("review-modal");
    if (modal) modal.classList.remove("hidden");
}

function closeReviewModal() {
    var modal = document.getElementById("review-modal");
    if (modal) modal.classList.add("hidden");
}

function setReviewRating(value) {
    _reviewRating = value;
    document.querySelectorAll("#review-star-picker .star-picker-btn").forEach(function (btn) {
        var starValue = parseInt(btn.getAttribute("data-value"), 10);
        btn.classList.toggle("active", starValue <= value);
    });
}

function submitReview(shopId) {
    var comment = document.getElementById("review-comment").value;
    if (!comment.trim()) {
        toast.error("Please write a comment for your review.");
        return;
    }
    var submitBtn = document.querySelector("#review-modal .modal-actions .btn-primary");
    if (submitBtn) submitBtn.disabled = true;

    postJson("/api/add-review", {
        shopId: shopId,
        rating: _reviewRating,
        comment: comment,
        stampPassport: true,
    })
        .then(function () {
            closeReviewModal();
            toast.success("Passport Stamped & Review Posted!");
            window.location.reload();
        })
        .catch(function (error) {
            if (submitBtn) submitBtn.disabled = false;
            toast.error(error.message);
        });
}

function voteOnVibe(shopId, vibe, vote, button) {
    postJson("/api/vibe-vote", { shopId: shopId, vibe: vibe, vote: vote })
        .then(function () {
            toast.success("Vote recorded! Refresh to see updated scores.");
        })
        .catch(function (error) { toast.error(error.message || "Could not save vibe vote."); });
}

function savePeopleSayRating(shopId, category, value, button) {
    postJson("/api/people-say-ratings", {
        shopId: shopId,
        ratings: (function () {
            var ratings = {};
            ratings[category] = value;
            return ratings;
        })(),
    })
        .then(function (data) {
            var starGroup = button.parentNode;
            starGroup.querySelectorAll(".people-say-star").forEach(function (star, index) {
                var icon = star.querySelector("i");
                icon.className = index < value ? "fas fa-star" : "far fa-star";
                star.classList.toggle("active", index < value);
            });
            var aggregate = data.ratings && data.ratings[category];
            var averageLabel = document.querySelector('[data-category-average="' + category + '"]');
            if (aggregate && averageLabel) {
                averageLabel.textContent = aggregate.average.toFixed(1) + " / 5 from " + aggregate.count + " " + (aggregate.count === 1 ? "rating" : "ratings");
            }
            toast.success("Rating saved!");
        })
        .catch(function (error) { toast.error(error.message || "Could not save rating."); });
}

function toggleFollow(userId, button) {
    postJson("/api/follow", { userId: userId })
        .then(function (data) {
            var icon = button.querySelector("i");
            var label = button.querySelector("span");
            if (data.following) {
                button.classList.remove("btn-primary");
                button.classList.add("btn-secondary");
                if (icon) icon.className = "fas fa-user-check";
                if (label) label.textContent = "Following";
                toast.success("Following!");
            } else {
                button.classList.remove("btn-secondary");
                button.classList.add("btn-primary");
                if (icon) icon.className = "fas fa-user-plus";
                if (label) label.textContent = "Follow";
                toast.success("Unfollowed!");
            }
        })
        .catch(function (error) { toast.error(error.message || "Could not update follow status."); });
}

/* ==================== SHOP DETAIL: GALLERY, LIGHTBOX, COMMUNITY TABS ==================== */

var _galleryFilter = "all";

function setGalleryFilter(filterValue) {
    _galleryFilter = filterValue;
    document.querySelectorAll("#gallery-filter .segmented-btn").forEach(function (btn) {
        btn.classList.toggle("active", btn.getAttribute("data-filter") === filterValue);
    });
    document.querySelectorAll("#gallery-grid .gallery-item").forEach(function (item) {
        var type = item.querySelector(".gallery-item-type");
        var typeText = type ? type.textContent.trim() : "";
        var visible = filterValue === "all" || typeText === filterValue;
        item.style.display = visible ? "" : "none";
    });
}

function setCommunityTab(tab) {
    document.querySelectorAll("#community-tabs .segmented-btn").forEach(function (btn) {
        btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
    });
    var visited = document.getElementById("community-visited");
    var saved = document.getElementById("community-saved");
    if (visited) visited.classList.toggle("hidden", tab !== "visited");
    if (saved) saved.classList.toggle("hidden", tab !== "saved");
}

var _lightboxImages = [];
var _lightboxIndex = 0;

function openLightbox(index) {
    var items = document.querySelectorAll("#gallery-grid .gallery-item img");
    _lightboxImages = Array.prototype.map.call(items, function (img) { return img.src; });
    if (_lightboxImages.length === 0) return;
    _lightboxIndex = Math.min(index, _lightboxImages.length - 1);
    renderLightbox();
    var lightbox = document.getElementById("lightbox");
    if (lightbox) lightbox.classList.remove("hidden");
}

function closeLightbox() {
    var lightbox = document.getElementById("lightbox");
    if (lightbox) lightbox.classList.add("hidden");
}

function nextLightboxImage() {
    if (_lightboxImages.length === 0) return;
    _lightboxIndex = (_lightboxIndex + 1) % _lightboxImages.length;
    renderLightbox();
}

function prevLightboxImage() {
    if (_lightboxImages.length === 0) return;
    _lightboxIndex = (_lightboxIndex - 1 + _lightboxImages.length) % _lightboxImages.length;
    renderLightbox();
}

function renderLightbox() {
    var img = document.getElementById("lightbox-image");
    var caption = document.getElementById("lightbox-caption");
    if (img) img.src = _lightboxImages[_lightboxIndex];
    if (caption) caption.textContent = (_lightboxIndex + 1) + " / " + _lightboxImages.length;
}

document.addEventListener("keydown", function (e) {
    var lightbox = document.getElementById("lightbox");
    if (!lightbox || lightbox.classList.contains("hidden")) return;
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowRight") nextLightboxImage();
    if (e.key === "ArrowLeft") prevLightboxImage();
});

function uploadShopPhoto(shopId, input) {
    if (!input.files || input.files.length === 0) return;
    var formData = new FormData();
    for (var i = 0; i < input.files.length; i++) {
        formData.append("images", input.files[i]);
    }
    toast.info("Uploading photo(s) for admin approval...");
    fetch("/shop/" + shopId + "/upload-photo", { method: "POST", body: formData })
        .then(function (response) {
            if (!response.ok) throw new Error("Upload failed.");
            toast.success("Photo(s) submitted for admin approval.");
            setTimeout(function () { window.location.reload(); }, 1200);
        })
        .catch(function (error) { toast.error(error.message || "Failed to upload photos."); });
}

/* ==================== ADMIN ACTIONS ==================== */

function approveImage(imageId, button) {
    postJson("/api/admin/approve-image", { imageId: imageId })
        .then(function () {
            var row = document.getElementById("pending-image-" + imageId);
            if (row) row.remove();
            toast.success("Image approved.");
        })
        .catch(function (error) { toast.error(error.message || "Could not approve image."); });
}

function adminDeleteImage(imageId, publicId, button) {
    if (!window.confirm("Delete this picture permanently?")) return;
    postJson("/api/admin/delete-image", { imageId: imageId, publicId: publicId })
        .then(function () {
            var row = document.getElementById("pending-image-" + imageId);
            if (row) row.remove();
            var galleryItem = button.closest(".gallery-item");
            if (galleryItem) galleryItem.remove();
            toast.success("Picture deleted.");
        })
        .catch(function (error) { toast.error(error.message || "Could not delete picture."); });
}

function approveClaim(requestId, button) {
    postJson("/api/admin/approve-claim", { requestId: requestId })
        .then(function () {
            var row = document.getElementById("claim-request-" + requestId);
            if (row) row.remove();
            toast.success("Claim request approved.");
        })
        .catch(function (error) { toast.error(error.message || "Could not approve claim request."); });
}

function adminHideShop(shopId, button) {
    if (!window.confirm("Hide this spot from public listings? Admins will still be able to see it.")) return;
    postJson("/api/admin/hide-shop", { shopId: shopId })
        .then(function () {
            toast.success("Spot hidden from public listings.");
            window.location.reload();
        })
        .catch(function (error) { toast.error(error.message || "Could not hide this spot."); });
}

function adminUnhideShop(shopId, button) {
    postJson("/api/admin/unhide-shop", { shopId: shopId })
        .then(function () {
            toast.success("Spot is public again.");
            window.location.reload();
        })
        .catch(function (error) { toast.error(error.message || "Could not unhide this spot."); });
}

function adminDeleteShop(shopId, shopName, button) {
    if (!window.confirm('Permanently delete "' + shopName + '"? This deletes all its photos, reviews, and saved/visited records. This cannot be undone.')) return;
    if (button) button.disabled = true;
    postJson("/api/admin/delete-shop", { shopId: shopId })
        .then(function () {
            var row = document.getElementById("admin-shop-" + shopId);
            if (row) row.remove();
            toast.success("Spot deleted.");
        })
        .catch(function (error) {
            toast.error(error.message || "Could not delete this spot.");
            if (button) button.disabled = false;
        });
}

/* ==================== GOOGLE MAPS URL -> LAT/LNG ==================== */


function updateLatLngFromMapsUrl(input) {
    var url = input.value.trim();
    if (!url) return;

    var patterns = [
        /!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/,
        /@(-?\d+\.\d+),(-?\d+\.\d+)/,
        /[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)/,
        /[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)/,
    ];

    for (var i = 0; i < patterns.length; i++) {
        var match = url.match(patterns[i]);
        if (match) {
            var latInput = document.getElementById("lat-input");
            var lngInput = document.getElementById("lng-input");
            if (latInput) latInput.value = match[1];
            if (lngInput) lngInput.value = match[2];
            toast.success("Pinpointed location from the map link.");
            return;
        }
    }

    toast.error("Could not read coordinates from that link. Try copying the URL after opening the pin in Google Maps.");
}

function openMapsSearchForNewSpot() {
    var nameInput = document.querySelector('input[name="name"]');
    var cityInput = document.querySelector('input[name="city"]');
    var name = nameInput ? nameInput.value.trim() : "";
    var city = cityInput ? cityInput.value.trim() : "";
    var query = [name, city].filter(Boolean).join(", ");

    var url = query
        ? "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(query)
        : "https://www.google.com/maps";

    if (!query) {
        toast.info("Enter the shop name and city first for a more accurate search.");
    }
    window.open(url, "_blank", "noopener,noreferrer");
}

/* ==================== ADD SPOT FORM ==================== */

function setupAddSpotForm() {
    var form = document.getElementById("add-spot-form");
    if (!form) return;

    var nameInput = form.querySelector('input[name="name"]');
    var cityInput = form.querySelector('input[name="city"]');
    var stateInput = form.querySelector('input[name="state"]');
    var areaInput = form.querySelector('input[name="area"]');

    [nameInput, cityInput, stateInput, areaInput].forEach(function (input) {
        if (!input) return;
        input.addEventListener("input", hideRestOfAddSpotForm);
    });

    form.addEventListener("submit", function (e) {
        var restSection = document.getElementById("add-spot-rest");
        var addressInput = form.querySelector('input[name="address"]');
        var imagesInput = document.getElementById("images-input");
        var vibeChecked = form.querySelectorAll('input[name="vibes"]:checked');

        if (restSection && restSection.classList.contains("hidden")) {
            e.preventDefault();
            toast.error("Please validate the shop name, city, and state first.");
            return;
        }
        if (!addressInput.value.trim()) {
            e.preventDefault();
            toast.error("Please paste the Google Maps URL for this spot.");
            return;
        }
        if (!imagesInput.files || imagesInput.files.length === 0) {
            e.preventDefault();
            toast.error("Please upload at least one photo.");
            return;
        }
        if (vibeChecked.length === 0) {
            e.preventDefault();
            toast.error("Please select at least one standard vibe.");
            return;
        }

        var submitBtn = document.getElementById("add-spot-submit");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Saving spot... <i class="fas fa-spinner fa-spin"></i>';
        }
    });

    form.querySelectorAll('input[name="vibes"]').forEach(function (checkbox) {
        checkbox.addEventListener("change", updateStandardVibeCount);
    });
    updateStandardVibeCount();
}

function hideDuplicateWarning() {
    var warningEl = document.getElementById("duplicate-shop-warning");
    if (warningEl) {
        warningEl.textContent = "";
        warningEl.classList.add("hidden");
    }
}

function hideRestOfAddSpotForm() {
    var restSection = document.getElementById("add-spot-rest");
    var validateBtn = document.getElementById("validate-spot-btn");
    var overrideInput = document.getElementById("duplicate-override-input");
    if (restSection) restSection.classList.add("hidden");
    if (validateBtn) {
        validateBtn.disabled = false;
        validateBtn.innerHTML = 'Validate <i class="fas fa-check"></i>';
    }
    if (overrideInput) overrideInput.value = "";
    hideDuplicateWarning();
}

function revealRestOfAddSpotForm() {
    var restSection = document.getElementById("add-spot-rest");
    if (restSection) restSection.classList.remove("hidden");
    hideDuplicateWarning();
    toast.success("Looks good! Add the rest of the details below.");
}

function blockDuplicateShopAndRedirect(message) {
    var warningEl = document.getElementById("duplicate-shop-warning");
    if (warningEl) {
        warningEl.textContent = message;
        warningEl.classList.remove("hidden");
    }
    toast.error(message);
    setTimeout(function () { window.location.href = "/"; }, 2500);
}

function validateAddSpotBasics() {
    var form = document.getElementById("add-spot-form");
    if (!form) return;

    var name = (form.querySelector('input[name="name"]') || {}).value || "";
    var city = (form.querySelector('input[name="city"]') || {}).value || "";
    var state = (form.querySelector('input[name="state"]') || {}).value || "";
    var area = (form.querySelector('input[name="area"]') || {}).value || "";
    name = name.trim(); city = city.trim(); state = state.trim(); area = area.trim();

    hideDuplicateWarning();

    if (!name || !city || !state) {
        toast.error("Please fill in the shop name, city, and state before validating.");
        return;
    }

    var validateBtn = document.getElementById("validate-spot-btn");
    if (validateBtn) {
        validateBtn.disabled = true;
        validateBtn.innerHTML = 'Checking... <i class="fas fa-spinner fa-spin"></i>';
    }

    postJson("/api/check-shop-duplicate", { name: name, city: city, area: area })
        .then(function (data) {
            if (data.status === "exact") {
                blockDuplicateShopAndRedirect(
                    'A shop named "' + data.matches[0].name + '" already exists in ' + city + ". You can't add a duplicate shop."
                );
                return;
            }
            if (data.status === "similar") {
                var match = data.matches[0];
                var sameShop = window.confirm(
                    'A shop named "' + match.name + '" already exists in ' + city + '. Is this the same shop?'
                );
                if (sameShop) {
                    blockDuplicateShopAndRedirect(
                        '"' + match.name + '" already exists in ' + city + ". You can't add a duplicate shop."
                    );
                    return;
                }
                var overrideInput = document.getElementById("duplicate-override-input");
                if (overrideInput) overrideInput.value = "true";
            }
            revealRestOfAddSpotForm();
            if (validateBtn) {
                validateBtn.disabled = false;
                validateBtn.innerHTML = 'Validated <i class="fas fa-check"></i>';
            }
        })
        .catch(function (error) {
            toast.error(error.message || "Could not check for duplicate shops. Please try again.");
            if (validateBtn) {
                validateBtn.disabled = false;
                validateBtn.innerHTML = 'Validate <i class="fas fa-check"></i>';
            }
        });
}

function updateStandardVibeCount() {
    var counter = document.getElementById("standard-vibe-count");
    if (!counter) return;
    var checked = document.querySelectorAll('input[name="vibes"]:checked').length;
    if (checked > 0) {
        counter.textContent = checked + " vibe" + (checked > 1 ? "s" : "") + " selected";
    } else {
        counter.textContent = "Select at least one vibe";
    }
}

function handleAddSpotImagePreview(input) {
    var grid = document.getElementById("photo-preview-grid");
    if (!grid || !input.files) return;

    Array.prototype.forEach.call(input.files, function (file) {
        var reader = new FileReader();
        var tile = document.createElement("div");
        tile.className = "photo-preview-tile";
        tile.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#a8988a;">' +
            '<i class="fas fa-spinner fa-spin"></i></div>';
        grid.appendChild(tile);

        reader.onload = function (e) {
            tile.innerHTML = '<img src="' + e.target.result + '" alt="Upload preview">';
        };
        reader.readAsDataURL(file);
    });

    toast.success(input.files.length + " photo(s) added");
}

function generateAiDescription() {
    var form = document.getElementById("add-spot-form") || document.querySelector("form.stacked-form");
    var nameInput = document.querySelector('input[name="name"]');
    var cityInput = document.querySelector('input[name="city"]');
    var button = document.getElementById("generate-ai-btn");

    if (!nameInput.value || !cityInput.value) return;

    button.disabled = true;
    button.innerHTML = '<i class="fas fa-magic"></i> Generating...';

    var formData = new FormData(form);

    fetch(window.location.pathname + "/generate-description", {
        method: "POST",
        body: formData,
    })
        .then(function (response) {
            if (!response.ok) throw new Error("Failed to generate description");
            return response.json();
        })
        .then(function (data) {
            var descriptionInput = document.getElementById("description-input");
            if (descriptionInput) descriptionInput.value = data.description;
            toast.success("Description generated!");
        })
        .catch(function () { toast.error("Failed to generate description"); })
        .finally(function () {
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-magic"></i> Generate with AI';
        });
}

function addCustomFacility() {
    var input = document.getElementById("custom-facility-input");
    var list = document.getElementById("custom-facility-list");
    var value = input.value.trim();
    if (!value) return;

    var label = document.createElement("label");
    label.className = "checkbox-label";
    label.innerHTML =
        '<input type="checkbox" name="custom_facilities" value="' + escapeHtml(value) + '" checked> ' +
        escapeHtml(value);
    list.appendChild(label);
    input.value = "";
}

/* ==================== PROFILE PAGE ==================== */

function startProfileEdit() {
    var editForm = document.getElementById("profile-edit-form");
    var viewBlock = document.getElementById("profile-view-block");
    var avatarEditBtn = document.getElementById("avatar-edit-btn");
    if (editForm) editForm.classList.remove("hidden");
    if (viewBlock) viewBlock.classList.add("hidden");
    if (avatarEditBtn) avatarEditBtn.classList.remove("hidden");
}

function cancelProfileEdit() {
    var editForm = document.getElementById("profile-edit-form");
    var viewBlock = document.getElementById("profile-view-block");
    var avatarEditBtn = document.getElementById("avatar-edit-btn");
    if (editForm) editForm.classList.add("hidden");
    if (viewBlock) viewBlock.classList.remove("hidden");
    if (avatarEditBtn) avatarEditBtn.classList.add("hidden");
}

function previewAvatarUpload(input) {
    if (!input.files || !input.files[0]) return;
    var file = input.files[0];

    if (!file.type.startsWith("image/")) {
        toast.error("Please upload an image file");
        input.value = "";
        return;
    }
    if (file.size > 5 * 1024 * 1024) {
        toast.error("Image must be smaller than 5MB");
        input.value = "";
        return;
    }

    var reader = new FileReader();
    reader.onload = function (e) {
        var preview = document.getElementById("profile-avatar-preview");
        if (preview) preview.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function shareProfile(username) {
    var url = window.location.origin + "/profile/" + username;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(function () {
            toast.success("Profile link copied to clipboard!");
        });
    } else {
        toast.info(url);
    }
}
