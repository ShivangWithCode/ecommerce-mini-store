function validateSignupForm() {
    const password = document.getElementById('password').value;
    if (password.length < 6) {
        alert("Password kam se kam 6 characters ka hona chahiye!");
        return false;
    }
    return true;
}