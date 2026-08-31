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
 *     { success, session_id, reply, stage, slots, options: [...], restaurants: [...] }
 *   POST {base}/reset { session_id } -> { success }
 *   Each restaurant in "restaurants" has: name, description, area, city,
 *   vibes, cheeky_vibes, rating, review_count, parking, facilities,
 *   maps_link.
 *
 * The backend now runs a guided Q&A: every question it asks comes back
 * with an "options" array of the only valid answers (sourced straight
 * from the database), and it expects the picked option's exact text back
 * as the next message. This widget renders those as clickable buttons
 * and hides the free-text input while a question with options is
 * pending, so the user can't type something outside the real data.
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
            addBubble("Hi! I'll ask a few quick questions to find the right match for you.", "bot");
            startGuidedQuestions();
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

    // Toggles the free-text input off while a guided question with option
    // buttons is pending, so the only way to answer is to pick one of the
    // real, database-backed choices.
    function setOptionsPending(pending) {
        form.classList.toggle("chatbot-input-row-hidden", pending);
        input.disabled = pending;
    }

    function renderOptions(options) {
        var wrap = document.createElement("div");
        wrap.className = "chatbot-options";

        options.forEach(function (optionText) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "chatbot-option-btn";
            btn.textContent = optionText;
            btn.addEventListener("click", function () {
                var buttons = wrap.querySelectorAll("button");
                for (var i = 0; i < buttons.length; i++) {
                    buttons[i].disabled = true;
                }
                sendMessage(optionText);
            });
            wrap.appendChild(btn);
        });

        messages.appendChild(wrap);
        scrollToBottom();
    }

    function scrollToBottom() {
        messages.scrollTop = messages.scrollHeight;
    }

    // options.silent skips rendering a user bubble for the message, used
    // for the initial kickoff call that just fetches the first guided
    // question and isn't something the user actually typed.
    function sendMessage(text, options) {
        options = options || {};
        if (!options.silent) {
            addBubble(text, "user");
        }
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
                    setOptionsPending(false);
                    return;
                }

                addBubble(data.reply, "bot");

                if (data.restaurants && data.restaurants.length > 0) {
                    addShopCards(data.restaurants);
                }

                if (data.options && data.options.length > 0) {
                    renderOptions(data.options);
                    setOptionsPending(true);
                } else {
                    setOptionsPending(false);
                }
            })
            .catch(function () {
                hideTyping();
                addBubble("I couldn't reach the recommendation service. Please try again in a moment.", "bot");
                setOptionsPending(false);
            });
    }

    // Kicks off the guided interview by asking the backend for the first
    // question. The message text itself is a placeholder the backend
    // ignores since no question has been asked yet in a fresh session.
    function startGuidedQuestions() {
        sendMessage("Hi", { silent: true });
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
        setOptionsPending(false);
        addBubble("Started a new conversation.", "bot");
        startGuidedQuestions();
    }

    launcher.addEventListener("click", togglePanel);

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        var text = input.value.trim();
        if (!text) return;
        input.value = "";
        input.disabled = true;
        sendMessage(text).finally(function () {
            if (!input.disabled) {
                input.focus();
            }
        });
    });

    if (resetBtn) {
        resetBtn.addEventListener("click", resetConversation);
    }
})();
