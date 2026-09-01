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

/* ==================== MAP (mirrors components/Map.tsx) ==================== */

var _map = null;
var _markers = [];

function initShopsMap(containerId, shops) {
    var container = document.getElementById(containerId);
    if (!container || typeof L === "undefined") return;

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

    _map.locate({ setView: true, maxZoom: 14 });
    _map.once("locationfound", function (e) {
        L.circleMarker(e.latlng, {
            radius: 8, fillColor: "#3b82f6", color: "#fff", weight: 2, opacity: 1, fillOpacity: 1,
        }).addTo(_map);
    });

    renderShopMarkers(shops || []);

    var locateBtn = document.getElementById("locate-me-btn");
    if (locateBtn) {
        locateBtn.addEventListener("click", function () {
            locateBtn.disabled = true;
            locateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            _map.locate({ setView: true, maxZoom: 14 });
            _map.once("locationfound", function (e) {
                locateBtn.disabled = false;
                locateBtn.innerHTML = '<i class="fas fa-location-arrow"></i>';
                L.circleMarker(e.latlng, {
                    radius: 8, fillColor: "#3b82f6", color: "#fff", weight: 2, opacity: 1, fillOpacity: 1,
                }).addTo(_map);
            });
            _map.once("locationerror", function () {
                locateBtn.disabled = false;
                locateBtn.innerHTML = '<i class="fas fa-location-arrow"></i>';
                toast.error("Could not access your location.");
            });
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

        var marker = L.marker([shop.location.lat, shop.location.lng], { icon: customIcon }).addTo(_map);
        marker.on("click", function () {
            window.location.href = "/shop/" + shop.id;
        });

        var imageUrl = (shop.gallery && shop.gallery[0] && shop.gallery[0].url) || "";
        var address = shop.location.address || "";
        var mapsUrl = address.indexOf("http") === 0
            ? address
            : "https://www.google.com/maps/search/?api=1&query=" +
              encodeURIComponent(shop.name + ", " + address + ", " + shop.location.city);

        var popupContent =
            '<div>' +
            '<div style="height:96px;width:100%;overflow:hidden;background:#eee;">' +
            '<img src="' + imageUrl + '" style="width:100%;height:100%;object-fit:cover;">' +
            "</div>" +
            '<div style="padding:0.75rem;">' +
            '<h3 style="margin:0 0 0.25rem;font-weight:700;">' + escapeHtml(shop.name) + "</h3>" +
            '<p style="margin:0 0 0.5rem;font-size:0.8rem;color:#8a7666;">' + escapeHtml(shop.location.city) + "</p>" +
            '<a href="' + mapsUrl + '" target="_blank" rel="noreferrer" ' +
            'style="font-size:0.75rem;font-weight:700;background:#F08000;padding:0.4rem 0.7rem;border-radius:8px;display:inline-block;">' +
            '<i class="fas fa-location-dot"></i> Location</a>' +
            "</div>" +
            "</div>";

        marker.bindPopup(popupContent);
        _markers.push(marker);
        markerGroup.addLayer(marker);
    });

    if (shops.length > 0) {
        try {
            var bounds = markerGroup.getBounds();
            if (bounds.isValid()) {
                _map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
            }
        } catch (e) {
            /* no-op, mirrors the try/catch around fitBounds in Map.tsx */
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
    if (isVisited) {
        markVisited(shopId, false);
    } else {
        openReviewModal(false);
    }
}

function markVisited(shopId, visited, rating, comment) {
    var payload = { shopId: shopId };
    if (rating) payload.rating = rating;
    if (comment) payload.comment = comment;

    return postJson("/api/visit-shop", payload).then(function (data) {
        var button = document.getElementById("visit-shop-btn");
        if (button) {
            button.setAttribute("data-visited", data.visited ? "true" : "false");
            var icon = button.querySelector("i");
            var label = button.querySelector("span");
            if (data.visited) {
                button.classList.remove("btn-outline");
                button.classList.add("btn-secondary");
                if (icon) icon.className = "fas fa-check-circle";
                if (label) label.textContent = "Visited";
            } else {
                button.classList.remove("btn-secondary");
                button.classList.add("btn-outline");
                if (icon) icon.className = "fas fa-stamp";
                if (label) label.textContent = "Stamp My Passport";
            }
        }
        return data;
    });
}

var _reviewRating = 5;
var _reviewOnlyMode = false;

function openReviewModal(reviewOnly) {
    _reviewOnlyMode = !!reviewOnly;
    var modal = document.getElementById("review-modal");
    var skipBtn = document.getElementById("review-skip-btn");
    if (skipBtn) skipBtn.classList.toggle("hidden", _reviewOnlyMode);
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
    var request = _reviewOnlyMode
        ? postJson("/api/add-review", { shopId: shopId, rating: _reviewRating, comment: comment })
        : markVisited(shopId, true, _reviewRating, comment);
    request
        .then(function () {
            closeReviewModal();
            toast.success(_reviewOnlyMode ? "Review Posted!" : "Passport Stamped & Review Posted!");
            if (_reviewOnlyMode) window.location.reload();
        })
        .catch(function (error) { toast.error(error.message); });
}

function skipReview(shopId) {
    markVisited(shopId, true)
        .then(function () {
            closeReviewModal();
            toast.success("Passport Stamped!");
        })
        .catch(function (error) { toast.error(error.message); });
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

    form.addEventListener("submit", function (e) {
        var addressInput = form.querySelector('input[name="address"]');
        var imagesInput = document.getElementById("images-input");
        var vibeChecked = form.querySelectorAll('input[name="vibes"]:checked');

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
