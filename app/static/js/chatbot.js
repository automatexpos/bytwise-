/*
 * Restaurant recommendation chatbot widget.
 *
 * Talks to the separate Flask + Ollama service (see the restaurant-ai
 * backend repo) at window.CHATBOT_API_URL, which is normally a Cloudflare
 * Tunnel URL pointing at that service while it runs on the developer's own
 * machine. Uses the same escapeHtml/toast helpers already defined in
 * app.js since this script loads after it.
 *
 * Contract with the backend:
 *   POST {base}/chat  { session_id, message } ->
 *     { success, session_id, reply, stage, slots, restaurants: [...] }
 *   POST {base}/reset { session_id } -> { success }
 *   Each restaurant in "restaurants" has: name, description, area, city,
 *   vibes, cheeky_vibes, rating, review_count, parking, facilities,
 *   maps_link.
 */

(function () {
    var API_BASE = (window.CHATBOT_API_URL || "").replace(/\/$/, "");
    if (!API_BASE) return;

    var launcher = document.getElementById("chatbot-launcher");
    var panel = document.getElementById("chatbot-panel");
    var messages = document.getElementById("chatbot-messages");
    var form = document.getElementById("chatbot-form");
    var input = document.getElementById("chatbot-input");
    var resetBtn = document.getElementById("chatbot-reset-btn");

    if (!launcher || !panel || !messages || !form || !input) return;

    var sessionId = localStorage.getItem("bytwise_chatbot_session_id");
    if (!sessionId) {
        sessionId = crypto.randomUUID();
        localStorage.setItem("bytwise_chatbot_session_id", sessionId);
    }

    var hasOpenedOnce = false;

    function togglePanel() {
        var isOpen = panel.classList.toggle("hidden") === false;
        launcher.classList.toggle("chatbot-launcher-open", isOpen);
        launcher.setAttribute("aria-expanded", isOpen ? "true" : "false");
        if (isOpen && !hasOpenedOnce) {
            hasOpenedOnce = true;
            addBubble("Hi! Tell me what kind of place you're looking for and I'll find a match.", "bot");
            input.focus();
        }
    }

    function addBubble(text, role) {
        var div = document.createElement("div");
        div.className = "chatbot-bubble chatbot-bubble-" + role;
        div.textContent = text;
        messages.appendChild(div);
        scrollToBottom();
    }

    function showTyping() {
        var div = document.createElement("div");
        div.className = "chatbot-typing";
        div.id = "chatbot-typing-indicator";
        div.innerHTML = "<span></span><span></span><span></span>";
        messages.appendChild(div);
        scrollToBottom();
    }

    function hideTyping() {
        var el = document.getElementById("chatbot-typing-indicator");
        if (el) el.remove();
    }

    function addShopCards(shops) {
        shops.forEach(function (shop) {
            var tags = (shop.vibes || []).concat(shop.cheeky_vibes || []).slice(0, 6);
            var card = document.createElement("div");
            card.className = "chatbot-shop-card";

            var metaBits = [];
            if (shop.area) metaBits.push(escapeHtml(shop.area) + (shop.city ? ", " + escapeHtml(shop.city) : ""));
            metaBits.push('<i class="fas fa-star"></i> ' + (shop.rating != null ? shop.rating : "n/a") +
                " (" + (shop.review_count || 0) + ")");

            card.innerHTML =
                '<div class="chatbot-shop-name">' + escapeHtml(shop.name || "") + "</div>" +
                '<div class="chatbot-shop-meta">' + metaBits.join(" &middot; ") + "</div>" +
                '<div class="chatbot-shop-tags">' +
                tags.map(function (t) { return '<span class="chatbot-shop-tag">' + escapeHtml(t) + "</span>"; }).join("") +
                "</div>";

            if (shop.maps_link) {
                var link = document.createElement("a");
                link.href = shop.maps_link;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.className = "chatbot-shop-link";
                link.innerHTML = '<i class="fas fa-location-dot"></i> View on map';
                card.appendChild(link);
            }

            messages.appendChild(card);
        });
        scrollToBottom();
    }

    function scrollToBottom() {
        messages.scrollTop = messages.scrollHeight;
    }

    function sendMessage(text) {
        addBubble(text, "user");
        showTyping();

        return fetch(API_BASE + "/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, message: text }),
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                hideTyping();

                if (!data.success) {
                    addBubble(data.error || "Something went wrong. Please try again.", "bot");
                    return;
                }

                addBubble(data.reply, "bot");

                if (data.restaurants && data.restaurants.length > 0) {
                    addShopCards(data.restaurants);
                }
            })
            .catch(function () {
                hideTyping();
                addBubble("I couldn't reach the recommendation service. Please try again in a moment.", "bot");
            });
    }

    function resetConversation() {
        fetch(API_BASE + "/reset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId }),
        }).catch(function () {
            // Ignore network errors here, reset locally regardless.
        });

        sessionId = crypto.randomUUID();
        localStorage.setItem("bytwise_chatbot_session_id", sessionId);
        messages.innerHTML = "";
        addBubble("Started a new conversation. Tell me what you're in the mood for.", "bot");
    }

    launcher.addEventListener("click", togglePanel);

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        var text = input.value.trim();
        if (!text) return;
        input.value = "";
        input.disabled = true;
        sendMessage(text).finally(function () {
            input.disabled = false;
            input.focus();
        });
    });

    if (resetBtn) {
        resetBtn.addEventListener("click", resetConversation);
    }
})();
