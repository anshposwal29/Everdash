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

// User Detail JS Functions
// Expand/collapse all conversations
function toggleAllGroups() {
    const groups = document.querySelectorAll('.collapsible-content');
    const icons = document.querySelectorAll('.group-icon');
    const btn = document.getElementById('global-toggle-btn');
    
    const isExpanding = btn.innerText === "Expand All";

    groups.forEach(group => {
        group.style.display = isExpanding ? "block" : "none";
    });

    icons.forEach(icon => {
        icon.innerText = isExpanding ? "▼" : "▶";
    });

    // Update the master button text
    btn.innerText = isExpanding ? "Collapse All" : "Expand All";
}

// Ensure existing single toggle function updates the master button if needed
function toggleDateGroup(id) {
    const group = document.getElementById(id);
    const icon = document.getElementById('icon-' + id);
    if (group.style.display === "none") {
        group.style.display = "block";
        icon.innerText = "▼";
    } else {
        group.style.display = "none";
        icon.innerText = "▶";
    }
}

// Determines which group of conversations to display
function applyRiskFilter(filterValue) {
    const conversations = document.querySelectorAll('.prompt-conversation-group');
    
    conversations.forEach(conv => {
        const hasRisk = conv.getAttribute('data-has-risk') === 'true';
        const isPassive = conv.getAttribute('data-is-passive') === 'true';

        if (filterValue === 'risky') {
            conv.style.display = hasRisk ? 'block' : 'none';
        } 
        else if (filterValue === 'passive-sensing') {
            conv.style.display = isPassive ? 'block' : 'none';
        }
        else if (filterValue === 'user-initiated') {
            conv.style.display = !isPassive ? 'block' : 'none';
        }
        else {
            conv.style.display = 'block';
        }
    });

    updateDateMarkers();
}

// Hides date headers if all corresponding conversations are hidden by the filter
function updateDateMarkers() {
    const markers = document.querySelectorAll('.timeline-date-marker');
    markers.forEach(marker => {
        // Look at all siblings until the next marker
        let nextEl = marker.nextElementSibling;
        let hasVisibleConvo = false;

        while (nextEl && !nextEl.classList.contains('timeline-date-marker')) {
            if (nextEl.classList.contains('prompt-conversation-group') && nextEl.style.display !== 'none') {
                hasVisibleConvo = true;
                break;
            }
            nextEl = nextEl.nextElementSibling;
        }

        marker.style.display = hasVisibleConvo ? 'block' : 'none';
    });
}