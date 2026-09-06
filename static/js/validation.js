function validateSignupForm() {
    const password = document.getElementById('password').value;
    if (password.length < 6) {
        alert("Password must be at least 6 characters long.");
        return false;
    }
    return true;
}