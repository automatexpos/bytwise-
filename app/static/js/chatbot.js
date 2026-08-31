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
 * The backend runs a conversational guided Q&A: every question it asks
 * comes back with an "options" array of the answers it can search by, but
 * those are only suggestions. The user can click one OR type a free-text
 * reply in their own words and the backend interprets it, so the input
 * box stays enabled the whole time. Clicking a suggestion is just a
 * shortcut for typing the same thing.
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
            addBubble("Hey there! Welcome to Bytwise.", "bot");
            // Small pause with a typing indicator so the greeting has a
            // moment to land before the first guided question shows up,
            // instead of both appearing back to back instantly.
            showTyping();
            setTimeout(function () {
                hideTyping();
                startGuidedQuestions();
            }, 900);
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

    // Keeps track of the most recently rendered set of suggestion
    // buttons so it can be disabled the moment the user answers (either
    // by clicking one or by typing something else instead), preventing a
    // stale suggestion from being clickable after the conversation has
    // already moved on to the next question.
    var activeOptionsWrap = null;

    function disableActiveOptions() {
        if (!activeOptionsWrap) return;
        var buttons = activeOptionsWrap.querySelectorAll("button");
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].disabled = true;
        }
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
                sendMessage(optionText);
            });
            wrap.appendChild(btn);
        });

        messages.appendChild(wrap);
        activeOptionsWrap = wrap;
        scrollToBottom();
    }

    function scrollToBottom() {
        messages.scrollTop = messages.scrollHeight;
    }

    // options.silent skips rendering a user bubble for the message, used
    // for the initial kickoff call that just fetches the first guided
    // question and isn't something the user actually typed.
    //
    // Whichever way the user answers (clicking a suggestion or typing
    // something themselves), any leftover suggestion buttons from the
    // previous question are disabled here so an old one can't be clicked
    // after the conversation has moved on, and the input is re-enabled
    // once the response comes back so the user is always free to type
    // the next reply.
    function sendMessage(text, options) {
        options = options || {};
        if (!options.silent) {
            addBubble(text, "user");
        }
        disableActiveOptions();
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

                if (data.options && data.options.length > 0) {
                    renderOptions(data.options);
                }
            })
            .catch(function () {
                hideTyping();
                addBubble("I couldn't reach the recommendation service. Please try again in a moment.", "bot");
            })
            .finally(function () {
                input.disabled = false;
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
        activeOptionsWrap = null;
        addBubble("Sure, let's start fresh.", "bot");
        showTyping();
        setTimeout(function () {
            hideTyping();
            startGuidedQuestions();
        }, 900);
    }

    launcher.addEventListener("click", togglePanel);

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        var text = input.value.trim();
        if (!text) return;
        input.value = "";
        input.disabled = true;
        sendMessage(text).finally(function () {
            input.focus();
        });
    });

    if (resetBtn) {
        resetBtn.addEventListener("click", resetConversation);
    }
})();
