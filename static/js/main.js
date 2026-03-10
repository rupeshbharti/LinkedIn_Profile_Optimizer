const loginTab = document.getElementById("login-tab");
const signupTab = document.getElementById("signup-tab");
const nameField = document.getElementById("name-field");
const formAction = document.getElementById("form-action");
const authSubmit = document.getElementById("auth-submit");

function setAuthMode(mode) {
  if (!loginTab || !signupTab || !nameField || !formAction || !authSubmit) return;
  const isSignup = mode === "signup";
  loginTab.classList.toggle("active", !isSignup);
  signupTab.classList.toggle("active", isSignup);
  nameField.classList.toggle("hidden", !isSignup);
  formAction.value = mode;
  authSubmit.textContent = isSignup ? "Create Account" : "Login";
}

if (loginTab && signupTab) {
  loginTab.addEventListener("click", () => setAuthMode("login"));
  signupTab.addEventListener("click", () => setAuthMode("signup"));
}

document.querySelectorAll(".copy-btn").forEach((button) => {
  button.addEventListener("click", () => {
    const targetId = button.getAttribute("data-copy-target");
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) return;
    navigator.clipboard.writeText(target.innerText.trim()).then(() => {
      button.textContent = "Copied";
      setTimeout(() => {
        button.textContent = "Copy";
      }, 1200);
    });
  });
});
