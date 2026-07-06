// main.js - Client side logic

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Theme Toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        // Check local storage for theme
        if (localStorage.getItem('theme') === 'dark') {
            document.body.classList.add('dark-mode');
            themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
        }

        themeToggle.addEventListener('click', () => {
            document.body.classList.toggle('dark-mode');
            if (document.body.classList.contains('dark-mode')) {
                localStorage.setItem('theme', 'dark');
                themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
            } else {
                localStorage.setItem('theme', 'light');
                themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
            }
        });
    }

    // Initialize SweetAlert for Flask Flashes
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        const category = msg.dataset.category;
        const text = msg.dataset.text;

        let icon = 'info';
        if (category === 'error' || category === 'danger') icon = 'error';
        if (category === 'success') icon = 'success';
        if (category === 'warning') icon = 'warning';

        if (category === 'danger' || category === 'error' || category === 'success') {
            Swal.fire({
                icon: icon,
                title: category === 'success' ? 'Success!' : 'Alert!',
                text: text,
                confirmButtonColor: category === 'success' ? '#2ecc71' : '#e74c3c'
            });
        } else {
            Swal.fire({
                icon: icon,
                title: text,
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 4000,
                timerProgressBar: true
            });
        }
    });

    // Password Toggle
    const togglePasswords = document.querySelectorAll('.toggle-password');
    togglePasswords.forEach(btn => {
        btn.addEventListener('click', function (e) {
            const targetId = this.getAttribute('data-target');
            const input = document.getElementById(targetId);
            const icon = this.querySelector('i');

            if (input.getAttribute('type') === 'password') {
                input.setAttribute('type', 'text');
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                input.setAttribute('type', 'password');
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });
    });

    // Password Strength Meter
    const passInput = document.getElementById('register-password');
    const strengthMeter = document.getElementById('strength-meter');
    if (passInput && strengthMeter) {
        passInput.addEventListener('input', () => {
            const val = passInput.value;
            let strength = 0;
            if (val.length > 5) strength += 1;
            if (val.match(/[a-z]+/)) strength += 1;
            if (val.match(/[A-Z]+/)) strength += 1;
            if (val.match(/[0-9]+/)) strength += 1;
            if (val.match(/[$@#&!]+/)) strength += 1;

            let meterHTML = '';
            const colors = ['#e74c3c', '#e67e22', '#f1c40f', '#2ecc71', '#27ae60'];
            for (let i = 0; i < 5; i++) {
                if (i < strength) {
                    meterHTML += `<div style="height: 5px; flex-grow: 1; margin: 0 2px; background-color: ${colors[strength - 1]}; border-radius: 3px;"></div>`;
                } else {
                    meterHTML += `<div style="height: 5px; flex-grow: 1; margin: 0 2px; background-color: #eee; border-radius: 3px;"></div>`;
                }
            }
            strengthMeter.innerHTML = `<div style="display:flex; width: 100%; margin-top: 5px;">${meterHTML}</div>`;
        });
    }

    // Form Submissions - Loading Overlay
    const loadForms = document.querySelectorAll('.show-loader');
    const loadOverlay = document.getElementById('loading-overlay');

    loadForms.forEach(form => {
        form.addEventListener('submit', (e) => {
            if (loadOverlay) {
                loadOverlay.classList.add('active');
            }
        });
    });

});

// Dynamic Circular Progress bar specific to AI analysis view
function animateCircularProgress(elementId, percentage, classification) {
    const circle = document.getElementById(elementId);
    if (!circle) return;

    let color = '#e74c3c'; // red - fake
    if (percentage >= 50 && percentage < 80) color = '#f39c12'; // yellow - suspicious
    if (percentage >= 80) color = '#2ecc71'; // green - genuine

    circle.style.background = `conic-gradient(${color} ${percentage}%, #eee ${percentage}%)`;
    circle.querySelector('.progress-value').innerText = `${percentage}%`;
    circle.querySelector('.progress-value').style.color = color;
}
