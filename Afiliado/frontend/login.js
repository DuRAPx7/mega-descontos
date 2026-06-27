const loginForm = document.querySelector("#loginForm");
const loginStatus = document.querySelector("#loginStatus");

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();

  fetch("/api/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      username: document.querySelector("#username").value,
      password: document.querySelector("#password").value
    })
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Usuario ou senha invalidos.");
      }
      return response.json();
    })
    .then(() => {
      window.location.href = "admin.html";
    })
    .catch((error) => {
      loginStatus.textContent = error.message;
    });
});
