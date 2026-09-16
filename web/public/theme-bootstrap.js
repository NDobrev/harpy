(function applyStoredTheme() {
  var theme = "dark_blue";
  try {
    var stored = window.localStorage.getItem("harpy.theme");
    if (stored === "white" || stored === "black" || stored === "dark_blue") {
      theme = stored;
    }
  } catch (error) {
    theme = "dark_blue";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
