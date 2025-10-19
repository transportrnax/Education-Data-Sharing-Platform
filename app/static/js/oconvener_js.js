document.addEventListener('DOMContentLoaded', function() {
    // --- cal fee ---
    function calculateFeeForModal(checkboxes, feeInputElement, feeStructure) {
        let totalFee = 0;
        if (!checkboxes || !feeInputElement) {
            console.warn("费用计算：复选框或费用输入框元素未找到。");
            return;
        }
        checkboxes.forEach(function(checkbox) {
            if (checkbox && checkbox.checked) {
                const feeForThisAccess = parseFloat(checkbox.getAttribute('data-fee') || "0");
                if (!isNaN(feeForThisAccess)) {
                    totalFee += feeForThisAccess;
                }
            }
        });
        feeInputElement.value = totalFee.toFixed(2);
    }

    // --- Add Member Modal JS ---
   const addMemberModal = document.getElementById('addMemberModal');
    const addMemberFormEl = document.getElementById('addMemberForm');
    const addAccessCheckboxesEl = document.querySelectorAll('.member-access-checkbox-add');
    const addPrivateProvideCheckbox = document.getElementById('add_modal_access_level_private_provide');
    const addPublicCheckbox = document.getElementById('add_modal_access_level_public');
    const addConsumeCheckbox = document.getElementById('add_modal_access_level_private_consume');
    const addFeeInputEl = document.getElementById('add_modal_membership_fee');
    const addFeeStructure = { public: 1000.00, consume: 100.00, provide: 0.00 };

    // Open the Add Member Modal
    const openAddMemberModalBtn = document.getElementById('openAddMemberModalBtn');
    const addModalCloseBtns = document.querySelectorAll('#addMemberModal .btn-close, #addMemberModal .add-modal-close-btn');
    
    if (openAddMemberModalBtn && addMemberModal) {
        openAddMemberModalBtn.addEventListener('click', function() {
            if (addMemberFormEl) addMemberFormEl.reset();

            // Calculate fee based on the current checkbox state
            if (typeof calculateFeeForModal === "function") {
                calculateFeeForModal(addAccessCheckboxesEl, addFeeInputEl, addFeeStructure);
            }

            addMemberModal.style.display = 'flex';
        });
    }

    // Close Add Member Modal on Close Button
    if (addModalCloseBtns) {
        addModalCloseBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                if (addMemberModal) addMemberModal.style.display = 'none';
            });
        });
    }

    // Ensure only one checkbox can be selected at a time
    addAccessCheckboxesEl.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            if (addPrivateProvideCheckbox.checked) {
                // If "Private Data Provide" is selected, uncheck the others
                addPublicCheckbox.checked = false;
                addConsumeCheckbox.checked = false;
            } else if (addPublicCheckbox.checked) {
                // If "Public Data Access" is selected, uncheck the others
                addPrivateProvideCheckbox.checked = false;
                addConsumeCheckbox.checked = false;
            } else if (addConsumeCheckbox.checked) {
                // If "Private Data Consume" is selected, uncheck the others
                addPrivateProvideCheckbox.checked = false;
                addPublicCheckbox.checked = false;
            }

            // Recalculate fee based on the new checkbox state
            if (typeof calculateFeeForModal === "function") {
                calculateFeeForModal(addAccessCheckboxesEl, addFeeInputEl, addFeeStructure);
            }
        });
    });

    // Close the modal when clicking outside the modal
    window.addEventListener('click', function(event) {
        if (event.target === addMemberModal) {
            addMemberModal.style.display = 'none';
        }
    });

    if (typeof SCRIPT_DATA !== 'undefined' && SCRIPT_DATA.showAddMemberModal === true && addMemberModal) {
        addMemberModal.style.display = 'flex';
        const addFormData = SCRIPT_DATA.addMemberFormData || {}; // 从 SCRIPT_DATA 获取

        const addEmailInput = document.getElementById('add_modal_member_email');
        const addUsernameInput = document.getElementById('add_modal_member_username');
        const addPublicCheckbox = document.getElementById('add_modal_access_level_public');
        const addConsumeCheckbox = document.getElementById('add_modal_access_level_private_consume');
        const addProvideCheckbox = document.getElementById('add_modal_access_level_private_provide');

        if (addEmailInput) addEmailInput.value = addFormData.email || '';
        if (addUsernameInput) addUsernameInput.value = addFormData.username || '';

        if (addPublicCheckbox) addPublicCheckbox.checked = (addFormData.access_level_public === 'on');
        if (addConsumeCheckbox) addConsumeCheckbox.checked = (addFormData.access_level_private_consume === 'on');
        if (addProvideCheckbox) addProvideCheckbox.checked = (addFormData.access_level_private_provide === 'on');

        if (typeof calculateFeeForModal === "function") {
            calculateFeeForModal(addAccessCheckboxesEl, addFeeInputEl, addFeeStructure);
        }
        if (addFeeInputEl && addFormData.membership_fee) {
            try {
                const feeVal = parseFloat(addFormData.membership_fee);
                if (!isNaN(feeVal)) addFeeInputEl.value = feeVal.toFixed(2);
            } catch (e) {
                console.warn("Failed to parse the membership fee ", e);
            }
        }
    }


    // --- Edit Member Modal JS ---
    const editMemberModalEl = document.getElementById('editMemberModal');
    const editMemberFormEl_no_ajax = document.getElementById('editMemberForm_no_ajax');
    const editModalCloseBtnsEl = document.querySelectorAll('#editMemberModal .btn-close, #editMemberModal .edit-modal-close-btn');

    const editFeeInputEl = document.getElementById('edit_modal_membership_fee');
    const editPublicAccessCheckboxEl = document.getElementById('edit_modal_access_level_public');
    const editPrivateConsumeCheckboxEl = document.getElementById('edit_modal_access_level_private_consume');
    const editPrivateProvideCheckboxEl = document.getElementById('edit_modal_access_level_private_provide');
    const editAccessCheckboxesEl = [editPublicAccessCheckboxEl, editPrivateConsumeCheckboxEl, editPrivateProvideCheckboxEl].filter(el => el != null); // Filter out non-existent elements
    const editFeeStructure = { public: 10.00, consume: 20.00, provide: 30.00 };

    // Ensure only one checkbox can be selected at a time
    editAccessCheckboxesEl.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            if (editPrivateProvideCheckboxEl.checked) {
                // If "Private Data Provide" is selected, uncheck the others
                editPublicAccessCheckboxEl.checked = false;
                editPrivateConsumeCheckboxEl.checked = false;
            } else if (editPublicAccessCheckboxEl.checked) {
                // If "Public Data Access" is selected, uncheck the others
                editPrivateProvideCheckboxEl.checked = false;
                editPrivateConsumeCheckboxEl.checked = false;
            } else if (editPrivateConsumeCheckboxEl.checked) {
                // If "Private Data Consume" is selected, uncheck the others
                editPrivateProvideCheckboxEl.checked = false;
                editPublicAccessCheckboxEl.checked = false;
            }

            // Recalculate fee based on the new checkbox state
            if (typeof calculateFeeForModal === "function") {
                calculateFeeForModal(editAccessCheckboxesEl, editFeeInputEl, editFeeStructure);
            }
        });
    });

    // Open the Edit Member Modal and populate fields
    document.querySelectorAll('.btn-open-edit-member-modal').forEach(button => {
        button.addEventListener('click', function() {
            if (!editMemberModalEl || !editMemberFormEl_no_ajax) {
                console.error("Error: Not find the modal");
                return;
            }

            editMemberFormEl_no_ajax.reset();

            const memberId = this.dataset.memberId;
            const email = this.dataset.email;
            const username = this.dataset.username;
            const accessPublic = this.dataset.accessPublic === 'true';
            const accessConsume = this.dataset.accessConsume === 'true';
            const accessProvide = this.dataset.accessProvide === 'true';

            const editEmailInput = document.getElementById('edit_modal_member_email');
            const editUsernameInput = document.getElementById('edit_modal_member_username');

            if (editEmailInput) editEmailInput.value = email || '';
            if (editUsernameInput) editUsernameInput.value = username || '';

            if (editPublicAccessCheckboxEl) editPublicAccessCheckboxEl.checked = accessPublic;
            if (editPrivateConsumeCheckboxEl) editPrivateConsumeCheckboxEl.checked = accessConsume;
            if (editPrivateProvideCheckboxEl) editPrivateProvideCheckboxEl.checked = accessProvide;

            // Recalculate fee
            if (typeof calculateFeeForModal === "function") {
                calculateFeeForModal(editAccessCheckboxesEl, editFeeInputEl, editFeeStructure);
            }

            // Set the form action for the edit member request
            if (memberId && typeof SCRIPT_DATA !== 'undefined' && SCRIPT_DATA.editMemberBaseUrl) {
                if (SCRIPT_DATA.editMemberBaseUrl.includes('MEMBER_ID_PLACEHOLDER')) {
                    editMemberFormEl_no_ajax.action = SCRIPT_DATA.editMemberBaseUrl.replace('MEMBER_ID_PLACEHOLDER', memberId);
                } else {
                    console.error("SCRIPT_DATA.editMemberBaseUrl not contain 'MEMBER_ID_PLACEHOLDER'.");
                    editMemberFormEl_no_ajax.action = "";
                }
            } else {
                console.error("The action for editing the form cannot be set. memberId or script_data.editMemberBaseUrl is missing.");
                editMemberFormEl_no_ajax.action = "";
            }

            // Show the modal
            editMemberModalEl.style.display = 'flex';
        });
    });

    if (editModalCloseBtnsEl) {
        editModalCloseBtnsEl.forEach(btn => {
            btn.addEventListener('click', function() {
                if (editMemberModalEl) editMemberModalEl.style.display = 'none';
            });
        });
    }

    if (typeof SCRIPT_DATA !== 'undefined' && SCRIPT_DATA.showEditMemberModalOnError && SCRIPT_DATA.showEditMemberModalOnError !== 'None' && SCRIPT_DATA.showEditMemberModalOnError !== null) {
        const memberIdToEditOnError = SCRIPT_DATA.showEditMemberModalOnError;
        const editMemberFormDataOnError = SCRIPT_DATA.editMemberFormDataOnError || {};

        if (editMemberModalEl && editMemberFormEl_no_ajax) {
            editMemberFormEl_no_ajax.reset();

            const editEmailInput = document.getElementById('edit_modal_member_email');
            const editUsernameInput = document.getElementById('edit_modal_member_username');

            if (editEmailInput) editEmailInput.value = editMemberFormDataOnError.email || '';
            if (editUsernameInput) editUsernameInput.value = editMemberFormDataOnError.username || '';

            if (editPublicAccessCheckboxEl) editPublicAccessCheckboxEl.checked = (editMemberFormDataOnError.access_level_public === 'on');
            if (editPrivateConsumeCheckboxEl) editPrivateConsumeCheckboxEl.checked = (editMemberFormDataOnError.access_level_private_consume === 'on');
            if (editPrivateProvideCheckboxEl) editPrivateProvideCheckboxEl.checked = (editMemberFormDataOnError.access_level_private_provide === 'on');

            if (typeof calculateFeeForModal === "function") {
                calculateFeeForModal(editAccessCheckboxesEl, editFeeInputEl, editFeeStructure);
            }
            if (editFeeInputEl && editMemberFormDataOnError.membership_fee) {
                try {
                    const feeVal = parseFloat(editMemberFormDataOnError.membership_fee);
                    if(!isNaN(feeVal)) editFeeInputEl.value = feeVal.toFixed(2);
                } catch (e) {
                    console.warn("Fee error", e);
                }
            }
            if (memberIdToEditOnError && typeof SCRIPT_DATA !== 'undefined' && SCRIPT_DATA.editMemberBaseUrl) {
                if (SCRIPT_DATA.editMemberBaseUrl.includes('MEMBER_ID_PLACEHOLDER')) {
                    editMemberFormEl_no_ajax.action = SCRIPT_DATA.editMemberBaseUrl.replace('MEMBER_ID_PLACEHOLDER', memberIdToEditOnError);
                } else {
                    console.error("No 'MEMBER_ID_PLACEHOLDER'。");
                    editMemberFormEl_no_ajax.action = "";
                }
            } else {
                console.error(" Lack memberIdToEditOnError/SCRIPT_DATA.editMemberBaseUrl");
                editMemberFormEl_no_ajax.action = "";
            }

            editMemberModalEl.style.display = 'flex';
        }
    }

    // --- Import Excel Modal JS ---
    const importExcelModal = document.getElementById('importExcelModal');
    const openImportExcelModalBtn = document.getElementById('openImportExcelModalBtn');
    const importExcelModalCloseBtns = document.querySelectorAll('#importExcelModal .btn-close, #importExcelModal .import-excel-modal-close-btn');
    const importExcelFormEl = document.getElementById('importExcelForm');

    if (openImportExcelModalBtn && importExcelModal) {
        openImportExcelModalBtn.addEventListener('click', function() {
            if (importExcelFormEl) {
                importExcelFormEl.reset(); 
            }
            importExcelModal.style.display = 'flex';
        });
    }

    if (importExcelModalCloseBtns) {
        importExcelModalCloseBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                if (importExcelModal) {
                    importExcelModal.style.display = 'none';
                }
            });
        });
    }

    // click outside close the window
    window.addEventListener('click', function(event) {
        if (addMemberModal && event.target == addMemberModal) { 
            addMemberModal.style.display = 'none';
        }
        if (editMemberModalEl && event.target == editMemberModalEl) { 
            editMemberModalEl.style.display = 'none';
        }
        if (importExcelModal && event.target == importExcelModal) { 
            importExcelModal.style.display = 'none';
        }
    });

    const serviceCheckboxes = document.querySelectorAll('.service-enable-checkbox');
    serviceCheckboxes.forEach(function(checkbox) {
        const scopeOptionsId = checkbox.dataset.targetScopes;
        const scopeOptionsDiv = document.getElementById(scopeOptionsId);

                // Function to handle state of controls within a scopeOptionsDiv
        function updateControlsState(currentCheckbox, panel) {
            const isChecked = currentCheckbox.checked;
            panel.style.display = isChecked ? 'block' : 'none';

                    // Handle radio buttons
            const radios = panel.querySelectorAll('input[type="radio"]');
            radios.forEach(radio => radio.disabled = !isChecked);

                    // Handle fee input (if it exists)
            const priceGroup = panel.querySelector('.price-input-group');
            if (priceGroup) {
                const feeInput = priceGroup.querySelector('input[type="number"]');
                if (feeInput) {
                    feeInput.disabled = !isChecked;
                    if (!isChecked) {
                        feeInput.value = "10.00"; // Or ""
                    }
                }
            }

                    // If the service is enabled and no scope is pre-selected, default to "Organization Only"
            if (isChecked) {
                let oneRadioChecked = false;
                radios.forEach(radio => {
                    if (radio.checked) oneRadioChecked = true;
                });
                if (!oneRadioChecked && radios.length > 0) {
                    const firstRadio = panel.querySelector('input[type="radio"][value="organization_only"]');
                    if (firstRadio) { // Prioritize 'organization_only' if available
                        firstRadio.checked = true;
                    } else if (radios.length > 0) { // Fallback to the very first radio
                        radios[0].checked = true;
                    }
                }
            }

                // Initial state based on checkbox (potentially set by Jinja)
            if (scopeOptionsDiv) {
                updateControlsState(checkbox, scopeOptionsDiv);
            }

                // Event listener for checkbox changes
            checkbox.addEventListener('change', function() {
                if (scopeOptionsDiv) {
                    updateControlsState(this, scopeOptionsDiv);
                }
            });
        }
    });
});