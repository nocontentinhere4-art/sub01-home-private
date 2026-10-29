// Halloween skin (owner 10-29), see halloween.css. Decorations only: absolute/fixed, aria-hidden, no clicks, static
// markup (never user content). The live page carries the announcement strip, tag and card in its own HTML (no layout
// shift); this script adds the decor and the strip's close button. Kimi hw1.
(function () {
  "use strict";
  var d = document, root = d.documentElement;
  root.classList.add("hw");
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var phone = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
  var A = ' aria-hidden="true" focusable="false"';
  var PUMPKIN = function (w, face) {
    return '<svg viewBox="0 0 64 56" width="' + w + '"' + A + (face ? ' class="lit"' : "") + '>' +
      '<path d="M30 9c0-5 3-8 7-8l1 3c-3 0-4 2-4 5z" fill="#3f6212"/>' +
      '<ellipse cx="18" cy="32" rx="14" ry="20" fill="#e2580b"/><ellipse cx="46" cy="32" rx="14" ry="20" fill="#e2580b"/>' +
      '<ellipse cx="32" cy="32" rx="15" ry="22" fill="#ff7a1a"/>' +
      '<path d="M32 11v42M20 14c-4 10-4 26 0 36M44 14c4 10 4 26 0 36" stroke="#c2410c" stroke-width="1.5" fill="none" opacity=".6"/>' +
      (face ? '<path d="M18 27l6-6 6 6zM34 27l6-6 6 6z" fill="#ffd166"/><path d="M17 37c5 7 25 7 30 0l-4 1-3 3-3-3-4 3-4-3-3 3-3-3z" fill="#ffd166"/>' : "") +
      "</svg>";
  };
  var BAT = '<svg viewBox="0 0 64 28"' + A + '><path d="M32 8c2-3 3-4 4-7 1 3 1 5 0 7 6-1 10-5 13-8 0 6 5 9 11 9-4 2-7 6-8 11-3-3-7-4-11-2-2-3-6-4-9-4s-7 1-9 4c-4-2-8-1-11 2-1-5-4-9-8-11 6 0 11-3 11-9 3 3 7 7 13 8-1-2-1-4 0-7 1 3 2 4 4 7z" fill="#120b1c" stroke="#8b5cf6" stroke-width=".8"/></svg>';
  var WEB = '<svg viewBox="0 0 100 100"' + A + ' class="hw-web" fill="none" stroke="#e9e4ff" stroke-width=".8">' +
    '<path d="M0 0l100 100M0 0l100 40M0 0l40 100M0 0l100 70M0 0l70 100"/>' +
    '<path d="M0 18q9 4 13 13 5-1 12 3 4-6 15-6"/><path d="M0 36q17 6 25 25 8-3 21 4 8-12 27-12"/><path d="M0 56q26 9 38 38 12-5 30 6 12-18 32-18"/></svg>';
  var SPIDER = '<svg viewBox="0 0 40 40"' + A + '><g stroke="#120b1c" stroke-width="2.2" fill="none" stroke-linecap="round">' +
    '<path d="M14 18L4 10M14 21L2 20M14 24L4 32M26 18l10-8M26 21l12-1M26 24l10 8"/></g>' +
    '<ellipse cx="20" cy="22" rx="8" ry="9" fill="#120b1c" stroke="#8b5cf6" stroke-width=".8"/><circle cx="17" cy="19" r="1.6" fill="#ff7a1a"/><circle cx="23" cy="19" r="1.6" fill="#ff7a1a"/></svg>';
  var HAT = '<svg viewBox="0 0 80 60" class="hw-hat"' + A + '><path d="M8 50c14-6 50-6 64 0-10 6-54 6-64 0z" fill="#1b1030" stroke="#8b5cf6"/>' +
    '<path d="M24 47L44 4c4 9 10 16 14 20-8 1-10 4-8 23z" fill="#1b1030" stroke="#8b5cf6"/><path d="M25 43c9-3 18-3 26 0l-1 5c-8-2-16-2-24 0z" fill="#ff7a1a"/></svg>';
  function el(html) { var t = d.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; }
  function add(parent, html) { if (parent) parent.appendChild(el(html)); }
  function closedStrip() { try { return sessionStorage.getItem("hw-strip") === "closed"; } catch (e) { return false; } }

  try {                                                    // favicon: a jack-o-lantern
    var ico = d.querySelector('link[rel="icon"]') || d.head.appendChild(d.createElement("link"));
    ico.rel = "icon";
    ico.href = "data:image/svg+xml," + encodeURIComponent(PUMPKIN(64, true).replace(A, ' xmlns="http://www.w3.org/2000/svg"'));
  } catch (e) {}

  var strip = d.getElementById("hw-strip");
  if (strip) {                                             // the live page
    if (closedStrip()) strip.hidden = true;
    var close = d.getElementById("hw-close");
    if (close) close.addEventListener("click", function () {
      strip.hidden = true; try { sessionStorage.setItem("hw-strip", "closed"); } catch (e) {}
    });
    if (d.getElementById("talk")) {                        // the relay's avatar page: pumpkins by its title
      root.classList.add("hw-avatar");
      add(d.querySelector(".wrap > header"), '<div class="hw-deco hw-pumpkins">' + PUMPKIN(30, true) + PUMPKIN(22) + PUMPKIN(36, true) + "</div>");
    }
    add(d.querySelector("header.top"), '<div class="hw-deco hw-spider"><i></i>' + SPIDER + "</div>");
    add(d.querySelector(".big"), HAT);
    var hype = d.getElementById("hype");
    if (hype && hype.firstChild && hype.firstChild.nodeType === 3) {   // "🔥 Hype" -> a lantern + " Hype"
      hype.firstChild.nodeValue = hype.firstChild.nodeValue.replace(/^\s*\S+\s*/, " ");
      hype.insertBefore(el(PUMPKIN(18, true)), hype.firstChild);
    }
    add(d.querySelector(".rail"), '<div class="hw-deco hw-pumpkins hw-rail-pk">' + PUMPKIN(34, true) + PUMPKIN(24) + PUMPKIN(30, true) + "</div>");
    add(d.getElementById("channel"), '<div class="hw-deco hw-pumpkins hw-ch-pk">' + PUMPKIN(22) + PUMPKIN(30, true) + PUMPKIN(40, true) + PUMPKIN(26) + "</div>");
    add(d.querySelector(".chat header"), WEB);
    d.querySelectorAll(".after .sec").forEach(function (s, i) { if (i % 2 === 0) add(s, WEB); });
    var empty = d.querySelector("#messages .empty"); if (empty) empty.textContent = "Say boo to SUB-01 👻";
  } else if (!closedStrip() && d.body) {                   // the other pages: a small fixed pill to the live page
    add(d.body, '<a class="hw-pill" href="https://subzerone.live/">' + PUMPKIN(22, true) + "<span>HALLOWEEN SPECIAL · Sat Oct 31 · guest KIMCHI</span></a>");
  }

  if (still || !d.body) return;                            // bats: never with reduced motion; one on a phone
  var layer = el('<div class="hw-deco hw-bats"></div>'); d.body.appendChild(layer);
  function flock() {
    if (!d.hidden) {
      for (var i = 0; i < (phone ? 1 : 3); i++) {
        var b = el('<div class="hw-bat">' + BAT + "</div>");
        b.style.top = (8 + Math.random() * 30) + "vh";
        b.style.animationDelay = (i * 0.45) + "s";
        b.style.animationDuration = (4.6 + Math.random() * 1.6) + "s";
        b.addEventListener("animationend", function (e) { if (e.target.classList.contains("hw-bat")) e.target.remove(); });
        layer.appendChild(b);
      }
    }
    setTimeout(flock, 30000 + Math.random() * 15000);
  }
  setTimeout(flock, 2500);
})();
