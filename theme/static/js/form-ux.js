(function () {
    'use strict';

    function cleanText(value) {
        return String(value || '').replace(/\s+/g, ' ').replace(/\*/g, '').trim();
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function fieldLabel(field) {
        if (!field) return 'Kolom';
        const aria = cleanText(field.getAttribute('aria-label'));
        if (aria) return aria;

        if (field.id) {
            const label = document.querySelector(`label[for="${CSS.escape(field.id)}"]`);
            if (label) {
                const text = cleanText(label.textContent);
                if (text) return text;
            }
        }

        const wrapper = field.closest('div, section, fieldset');
        if (wrapper) {
            const label = wrapper.querySelector('label');
            if (label) {
                const text = cleanText(label.textContent);
                if (text) return text;
            }
        }

        const placeholder = cleanText(field.getAttribute('placeholder'));
        if (placeholder && !/^masukkan\s/i.test(placeholder)) return placeholder;

        const name = field.getAttribute('name') || field.id || 'kolom';
        return name
            .replace(/^id_/, '')
            .replace(/[_-]+/g, ' ')
            .replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function isChoiceField(field) {
        return field && (field.tagName === 'SELECT' || field.type === 'radio' || field.type === 'checkbox');
    }

    function friendlyValidityMessage(field) {
        const label = fieldLabel(field);
        const validity = field.validity || {};

        if (validity.valueMissing) {
            return isChoiceField(field)
                ? `${label} wajib dipilih.`
                : `${label} wajib diisi.`;
        }
        if (validity.typeMismatch) return `Format ${label} tidak valid.`;
        if (validity.patternMismatch) return `${label} belum sesuai format yang diminta.`;
        if (validity.tooShort) return `${label} terlalu pendek.`;
        if (validity.tooLong) return `${label} terlalu panjang.`;
        if (validity.rangeUnderflow) return `${label} minimal ${field.min}.`;
        if (validity.rangeOverflow) return `${label} maksimal ${field.max}.`;
        if (validity.stepMismatch) return `Nilai ${label} tidak sesuai kelipatan yang diperbolehkan.`;
        if (validity.badInput) return `${label} berisi nilai yang tidak valid.`;
        return `${label} belum valid. Silakan periksa kembali.`;
    }

    function markInvalid(field) {
        if (!field) return;
        field.classList.add('posyandu-field-invalid');
        field.setAttribute('aria-invalid', 'true');
    }

    function clearInvalid(field) {
        if (!field) return;
        field.classList.remove('posyandu-field-invalid');
        field.removeAttribute('aria-invalid');
    }

    function findFieldByName(name) {
        if (!name) return null;
        const byId = document.getElementById(`id_${name}`) || document.getElementById(name);
        if (byId) return byId;
        try {
            return document.querySelector(`[name="${CSS.escape(name)}"]`);
        } catch (_error) {
            return null;
        }
    }

    function showValidationAlert(errors, options) {
        const normalized = (errors || []).filter((item) => item && item.message);
        if (!normalized.length || typeof Swal === 'undefined') return Promise.resolve();

        const seen = new Set();
        const unique = normalized.filter((item) => {
            const key = `${item.field || ''}|${item.label || ''}|${item.message}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        const html = `
            <div class="posyandu-validation-alert">
                <p class="posyandu-validation-intro">
                    Lengkapi atau perbaiki kolom yang ditandai sebelum menyimpan data.
                </p>
                <div class="posyandu-validation-list" role="list">
                    ${unique.map((item, index) => {
                        const label = cleanText(item.label) || 'Validasi data';
                        const message = cleanText(item.message);
                        let detail = message;

                        if (label && message.toLowerCase().startsWith(label.toLowerCase())) {
                            detail = message.slice(label.length).trim().replace(/^[:\-–—]\s*/, '');
                            if (detail) detail = detail.charAt(0).toUpperCase() + detail.slice(1);
                        }

                        return `
                            <div class="posyandu-validation-item" role="listitem">
                                <span class="posyandu-validation-number" aria-hidden="true">${index + 1}</span>
                                <div class="posyandu-validation-copy">
                                    <div class="posyandu-validation-label">${escapeHtml(label)}</div>
                                    <div class="posyandu-validation-message">${escapeHtml(detail || message)}</div>
                                </div>
                            </div>`;
                    }).join('')}
                </div>
            </div>`;

        return Swal.fire({
            icon: 'warning',
            title: (options && options.title) || 'Data Belum Lengkap',
            html: html,
            confirmButtonText: 'Periksa Kembali',
            confirmButtonColor: '#059669',
            allowOutsideClick: false,
            focusConfirm: true,
            customClass: {
                popup: 'posyandu-swal-validation',
                title: 'posyandu-swal-validation-title',
                htmlContainer: 'posyandu-swal-validation-content',
                actions: 'posyandu-swal-validation-actions',
                confirmButton: 'posyandu-swal-validation-confirm'
            }
        });
    }

    function addFallbackPlaceholder(field) {
        if (!field || field.disabled || field.readOnly || field.hasAttribute('placeholder')) return;
        if (!['INPUT', 'TEXTAREA'].includes(field.tagName)) return;
        const type = (field.type || 'text').toLowerCase();
        if (['hidden', 'checkbox', 'radio', 'file', 'date', 'time', 'color', 'range', 'submit', 'button', 'reset'].includes(type)) return;

        const label = fieldLabel(field);
        if (!label || label === 'Kolom') return;
        if (type === 'email') field.placeholder = 'contoh@email.com';
        else if (type === 'password') field.placeholder = `Masukkan ${label.toLowerCase()}`;
        else field.placeholder = `Masukkan ${label.toLowerCase()}`;
    }

    function improveSelectPrompt(select) {
        if (!select || select.tagName !== 'SELECT') return;
        const first = select.options && select.options[0];
        if (!first || String(first.value) !== '') return;
        const text = cleanText(first.textContent);
        if (text === '---------' || text === '-- Pilih --' || text === '') {
            first.textContent = `Pilih ${fieldLabel(select)}`;
        }
    }

    function protectIconSpacing(root) {
        (root || document).querySelectorAll('.relative').forEach((wrapper) => {
            const controls = wrapper.querySelectorAll(':scope > input, :scope > select, :scope > textarea');
            if (!controls.length) return;

            const leadingIcon = Array.from(wrapper.children).some((child) =>
                child.classList &&
                child.classList.contains('absolute') &&
                child.classList.contains('material-symbols-outlined') &&
                Array.from(child.classList).some((name) => name.startsWith('left-'))
            );
            const trailingAction = Array.from(wrapper.children).some((child) =>
                child.classList &&
                child.classList.contains('absolute') &&
                Array.from(child.classList).some((name) => name.startsWith('right-') || name === 'inset-y-0')
            );

            if (leadingIcon) wrapper.classList.add('posyandu-has-leading-icon');
            if (trailingAction) wrapper.classList.add('posyandu-has-trailing-action');
        });
    }

    function prepareForm(form) {
        if (!form || form.dataset.posyanduValidationReady === '1') return;
        form.dataset.posyanduValidationReady = '1';

        const method = String(form.getAttribute('method') || 'get').toLowerCase();
        const controls = Array.from(form.elements || []).filter((field) => field && field.matches && field.matches('input, select, textarea'));

        controls.forEach((field) => {
            addFallbackPlaceholder(field);
            improveSelectPrompt(field);
            field.addEventListener('input', () => {
                if (field.validity && field.validity.valid) clearInvalid(field);
            });
            field.addEventListener('change', () => {
                if (field.validity && field.validity.valid) clearInvalid(field);
            });
        });

        if (method !== 'post' || form.dataset.skipSwalValidation === 'true') return;

        // Disable the browser's native validation bubbles. Constraints remain
        // active and are checked manually below so feedback is consistently
        // presented with SweetAlert.
        form.noValidate = true;

        form.addEventListener('submit', function (event) {
            if (form.dataset.submitting === '1') return;

            const invalidFields = controls.filter((field) => {
                if (field.disabled || field.type === 'hidden' || !field.willValidate) return false;
                return field.validity && !field.validity.valid;
            });

            const customErrors = [];
            const checkboxGroupName = form.dataset.requireCheckboxGroup;
            if (checkboxGroupName) {
                const checkboxGroup = Array.from(form.querySelectorAll(`input[type="checkbox"][name="${CSS.escape(checkboxGroupName)}"]`));
                if (checkboxGroup.length && !checkboxGroup.some((box) => box.checked)) {
                    checkboxGroup.forEach(markInvalid);
                    customErrors.push({
                        field: checkboxGroupName,
                        label: form.dataset.checkboxGroupLabel || 'Pilihan',
                        message: `${form.dataset.checkboxGroupLabel || 'Pilihan'} wajib dipilih minimal satu.`
                    });
                }
            }

            if (!invalidFields.length && !customErrors.length) {
                form.dataset.submitting = '1';
                return;
            }

            event.preventDefault();
            invalidFields.forEach(markInvalid);
            const errors = invalidFields.map((field) => ({
                field: field.name || field.id,
                label: fieldLabel(field),
                message: friendlyValidityMessage(field)
            })).concat(customErrors);

            showValidationAlert(errors).then(() => {
                const first = invalidFields[0] || (checkboxGroupName ? form.querySelector(`input[type="checkbox"][name="${CSS.escape(checkboxGroupName)}"]`) : null);
                if (first && typeof first.focus === 'function') {
                    first.focus({ preventScroll: true });
                    first.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        });
    }

    function markServerErrors(errors) {
        (errors || []).forEach((item) => {
            const field = findFieldByName(item.field);
            if (field) markInvalid(field);
        });
    }

    window.PosyanduFormUX = {
        showValidationAlert,
        markServerErrors,
        fieldLabel,
        escapeHtml
    };

    document.addEventListener('DOMContentLoaded', function () {
        protectIconSpacing(document);
        document.querySelectorAll('form').forEach(prepareForm);
    });
})();
