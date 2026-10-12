/* Zify chat widget.
 *
 *   <script src="https://<zify host>/widget.js" data-shop="<shop slug>" async></script>
 *
 * Adds a round launcher to the corner of the page; clicking it opens the
 * shop's assistant in a frame served from the same host as this script.
 * Optional: data-position="left" puts it in the bottom-left corner.
 */
(function () {
  var script = document.currentScript
  if (!script || window.__zifyWidgetLoaded) return

  var shop = script.getAttribute("data-shop")
  if (!shop) return
  window.__zifyWidgetLoaded = true

  var origin = new URL(script.src).origin
  var side = script.getAttribute("data-position") === "left" ? "left" : "right"
  var BRAND = "#7c3aed"

  var CHAT_ICON =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-8 8H5l-2 2V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"/><path d="M8.5 11h7M8.5 14.5h4"/></svg>'
  var CLOSE_ICON =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>'

  function mount(info) {
    var open = false

    var button = document.createElement("button")
    button.type = "button"
    button.setAttribute("aria-label", "گفت‌وگو با دستیار فروشگاه")
    button.innerHTML = CHAT_ICON
    button.style.cssText =
      "all:initial;position:fixed;bottom:20px;" + side + ":20px;width:58px;height:58px;border-radius:50%;" +
      "background:" + BRAND + ";cursor:pointer;z-index:2147483646;display:flex;align-items:center;justify-content:center;" +
      "box-shadow:0 10px 30px rgba(124,58,237,.45);transition:transform .15s ease"
    button.onmouseenter = function () { button.style.transform = "scale(1.06)" }
    button.onmouseleave = function () { button.style.transform = "none" }

    var panel = document.createElement("div")
    panel.style.cssText =
      "all:initial;position:fixed;z-index:2147483647;display:none;overflow:hidden;background:#fff;" +
      "box-shadow:0 20px 60px rgba(0,0,0,.25)"

    var frame = document.createElement("iframe")
    frame.title = (info && info.name ? info.name + " - " : "") + "دستیار فروش"
    frame.style.cssText = "border:0;width:100%;height:100%;display:block"
    panel.appendChild(frame)

    // A phone gets the whole screen; anything wider gets a card above the button.
    function layout() {
      var small = window.innerWidth < 480
      panel.style.left = panel.style.right = ""
      if (small) {
        panel.style.top = "0"
        panel.style.bottom = "0"
        panel.style.left = "0"
        panel.style.right = "0"
        panel.style.width = "100%"
        panel.style.height = "100%"
        panel.style.borderRadius = "0"
        button.style.display = open ? "none" : "flex"
      } else {
        panel.style.top = ""
        panel.style.bottom = "92px"
        panel.style[side] = "20px"
        panel.style.width = "380px"
        panel.style.height = "min(620px, calc(100vh - 120px))"
        panel.style.borderRadius = "18px"
        button.style.display = "flex"
      }
    }

    function setOpen(next) {
      open = next
      // The frame is only loaded once somebody actually opens the chat.
      if (open && !frame.src) frame.src = origin + "/widget/" + encodeURIComponent(shop)
      panel.style.display = open ? "block" : "none"
      button.innerHTML = open ? CLOSE_ICON : CHAT_ICON
      button.setAttribute("aria-expanded", String(open))
      layout()
    }

    button.onclick = function () { setOpen(!open) }
    window.addEventListener("resize", layout)
    // On a phone the open chat covers the launcher, so the frame asks to close.
    window.addEventListener("message", function (event) {
      if (event.origin === origin && event.data === "zify-widget:close") setOpen(false)
    })

    document.body.appendChild(panel)
    document.body.appendChild(button)
    layout()
  }

  function start() {
    fetch(origin + "/api/widget/" + encodeURIComponent(shop))
      .then(function (res) { return res.json() })
      .then(function (info) { if (info && info.active) mount(info) })
      .catch(function () {})
  }

  if (document.body) start()
  else document.addEventListener("DOMContentLoaded", start)
})()
