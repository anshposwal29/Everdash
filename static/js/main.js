// Main JavaScript for Theradash

// Auto-hide alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});

// Utility function for making API calls
async function apiCall(url, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    const response = await fetch(url, options);
    return await response.json();
}

// Show loading indicator
function showLoading(element) {
    element.disabled = true;
    element.dataset.originalText = element.innerHTML;
    element.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading...';
}

// Hide loading indicator
function hideLoading(element) {
    element.disabled = false;
    if (element.dataset.originalText) {
        element.innerHTML = element.dataset.originalText;
    }
}

// Show toast notification (if using Bootstrap toasts)
function showNotification(message, type = 'info') {
    // Create toast element
    const toastHTML = `
        <div class="toast align-items-center text-white bg-${type} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;

    const toastContainer = document.getElementById('toast-container') ||
        (() => {
            const container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            document.body.appendChild(container);
            return container;
        })();

    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement);
    toast.show();

    // Remove toast element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', () => toastElement.remove());
}
