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

// ============================
// Global dashboard modal state (must be defined before any modal functions run)
// ============================
window.currentDashParticipantId = null;
window.currentSelectedTemplate = null;
window.currentParticipantDropped = false;
window.currentParticipantUtilization = null;

window.currentSelectedNoteType = null;

window.dashEmailParticipantData = null;
window.dashEmailTemplates = [];

// ============================
// Dashboard action modals
// ============================

function openDashboardEmailModal(participantId, identifier, utilization, dropped) {
    currentDashParticipantId = participantId;
    currentParticipantDropped = dropped === true || dropped === 'true' || dropped === 'True';
    currentParticipantUtilization = utilization || 'unknown';
    currentSelectedTemplate = null;

    const modal = document.getElementById('dashboard-email-modal');

    // Reset to step 1
    document.getElementById('dashEmailStep1').style.display = 'block';
    document.getElementById('dashEmailStep2').style.display = 'none';
    document.getElementById('dashEmailStep3').style.display = 'none';

    // Reset form
    document.getElementById('dashEmailTemplateSelect').value = '';
    document.getElementById('dashCustomMessageGroup').style.display = 'none';
    document.getElementById('dashCustomMessage').value = '';
    document.getElementById('dashPreviewEmailBtn').disabled = true;

    // Reset template card selection
    document.querySelectorAll('.template-card').forEach(card => {
        card.classList.remove('selected');
    });

    // Handle dropped warning
    const droppedWarning = document.getElementById('droppedWarningBanner');
    const droppedCheckbox = document.getElementById('droppedConfirmCheckbox');
    if (currentParticipantDropped) {
        droppedWarning.style.display = 'flex';
        droppedCheckbox.checked = false;
    } else {
        droppedWarning.style.display = 'none';
    }

    // Set utilization badge
    updateUtilizationBadge(currentParticipantUtilization);

    // Set initial display
    document.getElementById('dashEmailParticipantName').textContent = identifier ? `${identifier} (ID: ${participantId})` : `ID: ${participantId}`;

    // Show modal
    modal.style.display = 'block';

    // Load data
    loadDashboardEmailData(participantId);
}

function openDashboardNoteModal(participantId, identifier) {
    const modal = document.getElementById('dashboard-note-modal');
    const form = document.getElementById('dashNoteForm');

    // Reset form
    form.reset();
    currentSelectedNoteType = null;
    document.getElementById('dashNoteParticipantId').value = participantId;
    document.getElementById('dashNoteType').value = '';
    document.getElementById('dashNoteParticipantName').textContent = identifier ? `${identifier} (ID: ${participantId})` : `ID: ${participantId}`;

    // Reset note type card selection
    document.querySelectorAll('.note-type-card').forEach(card => {
        card.classList.remove('selected');
    });

    // Set default datetime to now
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('dashNoteDateTime').value = now.toISOString().slice(0, 16);

    modal.style.display = 'block';
}

// Dashboard actions helper functions


// Dashboard Email Modal Functions
//let dashEmailParticipantData = null;
//let dashEmailTemplates = [];
//let currentDashParticipantId = null;
//let currentSelectedTemplate = null;
//let currentParticipantDropped = false;
//let currentParticipantUtilization = null;


function updateUtilizationBadge(status) {
    const badge = document.getElementById('participantUtilizationBadge');
    badge.className = 'status-badge-lg';

    switch(status) {
        case 'never_utilized':
            badge.textContent = 'Never Used App';
            badge.classList.add('badge-never');
            break;
        case 'inactive_3plus':
            badge.textContent = '3+ Days Inactive';
            badge.classList.add('badge-inactive');
            break;
        case 'consistent':
            badge.textContent = 'Consistent User';
            badge.classList.add('badge-consistent');
            break;
        case 'moderate':
            badge.textContent = 'Moderate Use';
            badge.classList.add('badge-moderate');
            break;
        default:
            badge.textContent = 'Loading...';
    }
}

function selectTemplateCard(element, templateId) {
    // If dropped and not confirmed, don't allow selection
    if (currentParticipantDropped && !document.getElementById('droppedConfirmCheckbox').checked) {
        alert('Please confirm that you want to send an email to a dropped participant first.');
        return;
    }

    // Remove selection from all cards
    document.querySelectorAll('.template-card').forEach(card => {
        card.classList.remove('selected');
    });

    // Select this card
    element.classList.add('selected');
    currentSelectedTemplate = templateId;

    // Update hidden select
    document.getElementById('dashEmailTemplateSelect').value = templateId;

    // Show/hide custom message input
    const customGroup = document.getElementById('dashCustomMessageGroup');
    customGroup.style.display = templateId === 'custom' ? 'block' : 'none';

    // Enable preview button if email is available
    updatePreviewButtonState();
}

function onDroppedConfirmChange() {
    // If they uncheck after selecting a template, clear selection
    if (!document.getElementById('droppedConfirmCheckbox').checked && currentSelectedTemplate) {
        document.querySelectorAll('.template-card').forEach(card => {
            card.classList.remove('selected');
        });
        currentSelectedTemplate = null;
        document.getElementById('dashEmailTemplateSelect').value = '';
        document.getElementById('dashCustomMessageGroup').style.display = 'none';
        document.getElementById('dashPreviewEmailBtn').disabled = true;
    }
}

function updatePreviewButtonState() {
    const previewBtn = document.getElementById('dashPreviewEmailBtn');
    const hasTemplate = currentSelectedTemplate !== null;
    const hasEmail = dashEmailParticipantData && dashEmailParticipantData.email;
    const droppedOk = !currentParticipantDropped || document.getElementById('droppedConfirmCheckbox').checked;

    previewBtn.disabled = !(hasTemplate && hasEmail && droppedOk);
}

function closeDashboardEmailModal() {
    document.getElementById('dashboard-email-modal').style.display = 'none';
    dashEmailParticipantData = null;
    currentDashParticipantId = null;
}

function loadDashboardEmailData(participantId) {
    // Load participant info and templates in parallel
    Promise.all([
        fetch(`/api/email/participant/${participantId}`).then(r => r.json()),
        fetch('/api/email/templates').then(r => r.json())
    ]).then(([participantResponse, templatesResponse]) => {
        if (participantResponse.success) {
            dashEmailParticipantData = participantResponse.participant;

            // Update UI
            const firstName = dashEmailParticipantData.first_name || 'Unknown';
            document.getElementById('dashEmailParticipantName').textContent =
                `${firstName} (ID: ${participantId})`;
            document.getElementById('dashEmailToAddress').textContent =
                dashEmailParticipantData.email || 'No email available';

            // Last email sent
            if (dashEmailParticipantData.last_email_sent) {
                const lastEmailDate = formatDashDateTime(dashEmailParticipantData.last_email_sent);
                const lastEmailBy = dashEmailParticipantData.last_email_by || 'Unknown';
                document.getElementById('dashLastEmailSent').textContent =
                    `Last contact: ${lastEmailDate} by ${lastEmailBy}`;
            } else {
                document.getElementById('dashLastEmailSent').textContent = 'Last contact: Never';
            }

            // Update preview button state
            updatePreviewButtonState();
        } else {
            document.getElementById('dashEmailParticipantName').textContent = 'Error loading participant';
            document.getElementById('dashEmailToAddress').textContent = participantResponse.message || 'Error';
        }

        if (templatesResponse.success) {
            dashEmailTemplates = templatesResponse.templates;
            document.getElementById('dashEmailFromAddress').value = templatesResponse.from_address;

            // Populate hidden template dropdown for compatibility
            const select = document.getElementById('dashEmailTemplateSelect');
            select.innerHTML = '<option value="">-- Select a template --</option>';
            dashEmailTemplates.forEach(template => {
                const option = document.createElement('option');
                option.value = template.id;
                option.textContent = template.name;
                select.appendChild(option);
            });
        }
    }).catch(error => {
        console.error('Error loading email data:', error);
        document.getElementById('dashEmailParticipantName').textContent = 'Error loading data';
        document.getElementById('dashEmailToAddress').textContent = error.message;
    });
}

function formatDashDateTime(dateStr) {
    if (!dateStr) return '';
    try {
        const date = new Date(dateStr);
        return date.toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    } catch (e) {
        return dateStr;
    }
}

function onDashTemplateChange() {
    const templateId = document.getElementById('dashEmailTemplateSelect').value;
    const descriptionEl = document.getElementById('dashTemplateDescription');
    const customGroup = document.getElementById('dashCustomMessageGroup');
    const previewBtn = document.getElementById('dashPreviewEmailBtn');

    if (!templateId) {
        descriptionEl.textContent = '';
        customGroup.style.display = 'none';
        previewBtn.disabled = true;
        return;
    }

    // Find template and show description
    const template = dashEmailTemplates.find(t => t.id === templateId);
    if (template) {
        descriptionEl.textContent = template.description;
    }

    // Show custom message field for custom template
    customGroup.style.display = templateId === 'custom' ? 'block' : 'none';

    // Enable preview button if email is available
    previewBtn.disabled = !dashEmailParticipantData || !dashEmailParticipantData.email;
}

function dashPreviewEmail() {
    const templateId = document.getElementById('dashEmailTemplateSelect').value;
    const customMessage = document.getElementById('dashCustomMessage').value;

    if (!templateId || !dashEmailParticipantData) return;

    // Get RA name
    let raName = dashEmailParticipantData.research_assistant || 'The Research Team';

    const requestData = {
        template_id: templateId,
        first_name: dashEmailParticipantData.first_name,
        ra_first_name: raName,
        username: dashEmailParticipantData.username || '',
        password: dashEmailParticipantData.password || '',
        custom_message: customMessage
    };

    fetch('/api/email/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show step 2
            document.getElementById('dashEmailStep1').style.display = 'none';
            document.getElementById('dashEmailStep2').style.display = 'block';

            // Populate editable preview
            document.getElementById('dashPreviewToAddress').textContent = dashEmailParticipantData.email;
            document.getElementById('dashPreviewFromAddress').textContent = data.from_address;
            document.getElementById('dashPreviewSubject').value = data.subject;
            document.getElementById('dashPreviewBodyVisual').innerHTML = data.body;
            document.getElementById('dashPreviewBodyHtml').value = data.body;

            // Reset to visual editor
            toggleEditor('visual');
        } else {
            alert('Error generating preview: ' + data.message);
        }
    })
    .catch(error => {
        alert('Error generating preview: ' + error.message);
    });
}

function toggleEditor(mode) {
    const visualEditor = document.getElementById('dashPreviewBodyVisual');
    const htmlEditor = document.getElementById('dashPreviewBodyHtml');
    const visualBtn = document.getElementById('visualEditorBtn');
    const htmlBtn = document.getElementById('htmlEditorBtn');

    if (mode === 'visual') {
        // Switching to visual - update visual from HTML
        visualEditor.innerHTML = htmlEditor.value;
        visualEditor.style.display = 'block';
        htmlEditor.style.display = 'none';
        visualBtn.classList.add('active');
        htmlBtn.classList.remove('active');
    } else {
        // Switching to HTML - update HTML from visual
        htmlEditor.value = visualEditor.innerHTML;
        visualEditor.style.display = 'none';
        htmlEditor.style.display = 'block';
        visualBtn.classList.remove('active');
        htmlBtn.classList.add('active');
    }
}

function dashBackToStep1() {
    document.getElementById('dashEmailStep1').style.display = 'block';
    document.getElementById('dashEmailStep2').style.display = 'none';
}

function dashSendEmail() {
    const templateId = document.getElementById('dashEmailTemplateSelect').value;
    const subject = document.getElementById('dashPreviewSubject').value;

    // Get body from whichever editor is currently visible
    const visualEditor = document.getElementById('dashPreviewBodyVisual');
    const htmlEditor = document.getElementById('dashPreviewBodyHtml');
    let body;

    if (htmlEditor.style.display !== 'none') {
        // HTML editor is active - use its value
        body = htmlEditor.value;
    } else {
        // Visual editor is active - use its innerHTML
        body = visualEditor.innerHTML;
    }

    // Show step 3 with sending indicator
    document.getElementById('dashEmailStep2').style.display = 'none';
    document.getElementById('dashEmailStep3').style.display = 'block';
    document.getElementById('dashEmailSendingIndicator').style.display = 'flex';
    document.getElementById('dashEmailSuccessIndicator').style.display = 'none';
    document.getElementById('dashEmailErrorIndicator').style.display = 'none';
    document.getElementById('dashEmailStep3Buttons').style.display = 'none';

    const requestData = {
        participant_id: currentDashParticipantId,
        to_email: dashEmailParticipantData.email,
        subject: subject,
        body: body,
        template_id: templateId,
        password: dashEmailParticipantData.password || ''
    };

    fetch('/api/email/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('dashEmailSendingIndicator').style.display = 'none';
        document.getElementById('dashEmailStep3Buttons').style.display = 'flex';

        if (data.success) {
            document.getElementById('dashEmailSuccessIndicator').style.display = 'flex';
        } else {
            document.getElementById('dashEmailErrorIndicator').style.display = 'flex';
            document.getElementById('dashEmailErrorMessage').textContent = data.message || 'Error sending email';
        }
    })
    .catch(error => {
        document.getElementById('dashEmailSendingIndicator').style.display = 'none';
        document.getElementById('dashEmailErrorIndicator').style.display = 'flex';
        document.getElementById('dashEmailErrorMessage').textContent = error.message;
        document.getElementById('dashEmailStep3Buttons').style.display = 'flex';
    });
}

// Dashboard Note Modal Functions
//let currentSelectedNoteType = null;


function selectNoteType(element, noteType) {
    // Remove selection from all cards
    document.querySelectorAll('.note-type-card').forEach(card => {
        card.classList.remove('selected');
    });

    // Select this card
    element.classList.add('selected');
    currentSelectedNoteType = noteType;
    document.getElementById('dashNoteType').value = noteType;
}

function closeDashboardNoteModal() {
    document.getElementById('dashboard-note-modal').style.display = 'none';
    currentSelectedNoteType = null;
}

function saveDashboardNote() {
    const noteData = {
        participant_id: document.getElementById('dashNoteParticipantId').value,
        note_type: document.getElementById('dashNoteType').value,
        note_reason: document.getElementById('dashNoteReason').value,
        datetime: document.getElementById('dashNoteDateTime').value,
        duration: document.getElementById('dashNoteDuration').value,
        note: document.getElementById('dashNoteContent').value
    };

    fetch('/api/notes', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(noteData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            closeDashboardNoteModal();
            alert('Note saved successfully!');
        } else {
            alert('Error saving note: ' + data.message);
        }
    })
    .catch(error => {
        alert('Error saving note: ' + error.message);
    });
}
