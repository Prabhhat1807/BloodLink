/**
 * BloodLink — Blood Donation & Emergency Finder
 * Main Client-Side JavaScript
 * Module 1: Dashboard Overview & Live Telemetry (GET /dashboard/stats)
 * Module 2: Live Donor Search & Ranking (Bubble Sort)
 * Module 3: Voluntary Donor Registration (Form validation & POST /donors)
 * Module 4: Donor Management & Availability (GET/PUT/PATCH /donors)
 * Module 5: Emergency Requests & Live Board (Form broadcast & GET/POST/PUT /emergency)
 */

document.addEventListener('DOMContentLoaded', function () {
  initDashboardOverview();
  initDonorSearch();
  initDonorRegistration();
  initDonorManagement();
  initRecipientRegistration();
  initRecipientManagement();
  initEmergencyRequests();
});

// ========================================================
// Module 1: Donor Search & Compatibility Engine
// ========================================================
function initDonorSearch() {
  var searchForm = document.getElementById('donor-search-form');
  if (!searchForm) return;

  var bloodGroupSelect = document.getElementById('search-blood-group');
  var locationInput = document.getElementById('search-location');

  var resultsPlaceholder = document.getElementById('results-placeholder');
  var resultsLoading = document.getElementById('results-loading');
  var resultsError = document.getElementById('results-error');
  var resultsEmpty = document.getElementById('results-empty');
  var resultsContent = document.getElementById('results-content');
  var donorCardsContainer = document.getElementById('donor-cards-container');

  var resultsSummaryTitle = document.getElementById('results-summary-title');
  var resultsSummarySubtitle = document.getElementById('results-summary-subtitle');
  var resultsCountBadge = document.getElementById('results-count-badge');
  var errorMessage = document.getElementById('error-message');
  var emptyMessage = document.getElementById('empty-message');

  /**
   * Toggle between result display states
   * @param {string} state - 'placeholder' | 'loading' | 'error' | 'empty' | 'content'
   */
  function setResultsState(state) {
    if (resultsPlaceholder) resultsPlaceholder.style.display = (state === 'placeholder') ? 'block' : 'none';
    if (resultsLoading) resultsLoading.style.display = (state === 'loading') ? 'block' : 'none';
    if (resultsError) resultsError.style.display = (state === 'error') ? 'flex' : 'none';
    if (resultsEmpty) resultsEmpty.style.display = (state === 'empty') ? 'block' : 'none';
    if (resultsContent) resultsContent.style.display = (state === 'content') ? 'block' : 'none';
  }

  // Handle Form Submission
  searchForm.addEventListener('submit', function (e) {
    e.preventDefault();

    var bloodGroup = bloodGroupSelect ? bloodGroupSelect.value.trim() : '';
    var location = locationInput ? locationInput.value.trim() : '';

    if (!bloodGroup) {
      setResultsState('error');
      if (errorMessage) errorMessage.textContent = 'Please select a required blood group from the dropdown list.';
      return;
    }

    // Show loading indicator
    setResultsState('loading');

    // Build URL safely with URLSearchParams
    var params = new URLSearchParams();
    params.append('blood_group', bloodGroup);
    if (location) {
      params.append('location', location);
    }

    var requestUrl = '/find-donors?' + params.toString();

    // Send request to existing Flask backend
    fetch(requestUrl)
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (errData) {
            throw new Error(errData.error || ('Server returned HTTP ' + response.status));
          }).catch(function () {
            throw new Error('Server returned HTTP ' + response.status);
          });
        }
        return response.json();
      })
      .then(function (data) {
        if (!data.donors || data.donors.length === 0) {
          setResultsState('empty');
          if (emptyMessage) {
            emptyMessage.textContent = 'No compatible active donors found for blood group ' +
              data.recipient_blood_group + (data.location ? ' in ' + data.location : '') + '.';
          }
          return;
        }

        renderDonorCards(data);
      })
      .catch(function (error) {
        setResultsState('error');
        if (errorMessage) errorMessage.textContent = 'Error connecting to search service: ' + error.message;
      });
  });

  /**
   * Safely render donor cards using textContent to prevent XSS
   * @param {Object} data - Backend response containing recipient_blood_group, location, total_matches, donors
   */
  function renderDonorCards(data) {
    if (!donorCardsContainer) return;

    // Clear previous results safely
    while (donorCardsContainer.firstChild) {
      donorCardsContainer.removeChild(donorCardsContainer.firstChild);
    }

    // Update section summary
    if (resultsSummaryTitle) resultsSummaryTitle.textContent = 'Compatible Donors Found';
    if (resultsSummarySubtitle) {
      resultsSummarySubtitle.textContent = 'Displaying donors biologically compatible with blood group ' +
        data.recipient_blood_group + (data.location ? ' in "' + data.location + '"' : '') +
        ', ranked by Python matching score (Bubble Sort).';
    }

    var matchCount = data.total_matches || data.donors.length;
    if (resultsCountBadge) {
      resultsCountBadge.textContent = matchCount + (matchCount === 1 ? ' Match' : ' Matches');
    }

    // Create cards for each matched donor
    data.donors.forEach(function (donor, index) {
      var card = document.createElement('div');
      card.className = 'donor-result-card';

      // Card Header: Blood badge & score pill
      var cardTop = document.createElement('div');
      cardTop.className = 'donor-card-top';

      var bloodBadge = document.createElement('div');
      bloodBadge.className = 'donor-blood-badge';
      bloodBadge.textContent = donor.blood_group || 'N/A';

      var scoreBox = document.createElement('div');
      scoreBox.className = 'donor-score-box';

      var scoreVal = document.createElement('div');
      scoreVal.className = 'donor-score-val';
      scoreVal.textContent = (donor.matching_score !== undefined ? donor.matching_score : 0) + ' pts';

      var scoreRank = document.createElement('div');
      scoreRank.className = 'donor-score-rank';
      scoreRank.textContent = 'Rank #' + (index + 1);

      scoreBox.appendChild(scoreVal);
      scoreBox.appendChild(scoreRank);

      cardTop.appendChild(bloodBadge);
      cardTop.appendChild(scoreBox);
      card.appendChild(cardTop);

      // Donor Name & Non-sensitive ID
      var nameHeading = document.createElement('h4');
      nameHeading.className = 'donor-card-name';
      nameHeading.textContent = donor.name ? donor.name : ('Donor #' + donor.donor_id);
      card.appendChild(nameHeading);

      var idBadge = document.createElement('div');
      idBadge.className = 'donor-id-pill';
      idBadge.textContent = 'Donor ID: #' + donor.donor_id;
      card.appendChild(idBadge);

      // Donor details list
      var detailsList = document.createElement('ul');
      detailsList.className = 'donor-details-list';

      // Location detail
      var locItem = document.createElement('li');
      var locLabel = document.createElement('span');
      locLabel.className = 'detail-label';
      locLabel.textContent = 'Location:';
      var locValue = document.createElement('span');
      locValue.className = 'detail-value';
      locValue.textContent = donor.location || 'Not Specified';
      locItem.appendChild(locLabel);
      locItem.appendChild(locValue);
      detailsList.appendChild(locItem);

      // Status detail
      var statusItem = document.createElement('li');
      var statusLabel = document.createElement('span');
      statusLabel.className = 'detail-label';
      statusLabel.textContent = 'Availability:';
      var statusValue = document.createElement('span');
      statusValue.className = 'status-tag-active';
      statusValue.textContent = (donor.availability === 1) ? 'Active Donor' : 'Inactive';
      statusItem.appendChild(statusLabel);
      statusItem.appendChild(statusValue);
      detailsList.appendChild(statusItem);

      // Medical / Health status detail
      if (donor.medical_status) {
        var medItem = document.createElement('li');
        var medLabel = document.createElement('span');
        medLabel.className = 'detail-label';
        medLabel.textContent = 'Health Status:';
        var medValue = document.createElement('span');
        medValue.className = 'detail-value';
        medValue.textContent = donor.medical_status;
        medItem.appendChild(medLabel);
        medItem.appendChild(medValue);
        detailsList.appendChild(medItem);
      }

      // Match type explanation
      var matchItem = document.createElement('li');
      var matchLabel = document.createElement('span');
      matchLabel.className = 'detail-label';
      matchLabel.textContent = 'Match Factor:';
      var matchValue = document.createElement('span');
      matchValue.className = 'detail-value match-factor-text';

      var isExact = (donor.blood_group === data.recipient_blood_group);
      var isSameCity = data.location && donor.location &&
        (donor.location.toLowerCase() === data.location.toLowerCase());

      var explanation = isExact ? 'Exact Blood (+60)' : 'Compatible Blood (+40)';
      if (isSameCity) {
        explanation += ' & Same City (+20)';
      }
      matchValue.textContent = explanation;
      matchItem.appendChild(matchLabel);
      matchItem.appendChild(matchValue);
      detailsList.appendChild(matchItem);

      card.appendChild(detailsList);
      donorCardsContainer.appendChild(card);
    });

    // Display the results container
    setResultsState('content');
  }
}

// ========================================================
// Module 2: Voluntary Donor Registration
// ========================================================
function initDonorRegistration() {
  var regForm = document.getElementById('donor-registration-form');
  if (!regForm) return;

  // Form input fields
  var inputName = document.getElementById('reg-name');
  var inputAge = document.getElementById('reg-age');
  var inputBloodGroup = document.getElementById('reg-blood-group');
  var inputPhone = document.getElementById('reg-phone');
  var inputLocation = document.getElementById('reg-location');
  var selectGender = document.getElementById('reg-gender');
  var inputWeight = document.getElementById('reg-weight');
  var inputLastDonation = document.getElementById('reg-last-donation');
  var selectAvailability = document.getElementById('reg-availability');
  var inputMedicalStatus = document.getElementById('reg-medical-status');

  // Feedback and alert containers
  var successAlert = document.getElementById('register-success');
  var successTitle = document.getElementById('register-success-title');
  var successMessage = document.getElementById('register-success-message');
  var assignedIdPill = document.getElementById('assigned-donor-id');

  var errorAlert = document.getElementById('register-error');
  var errorTitle = document.getElementById('register-error-title');
  var errorMessage = document.getElementById('register-error-message');

  // Submit and Reset buttons
  var submitBtn = document.getElementById('btn-submit-donor');
  var resetBtn = document.getElementById('btn-reset-donor');
  var btnText = submitBtn ? submitBtn.querySelector('.btn-text') : null;
  var btnSpinner = submitBtn ? submitBtn.querySelector('.btn-spinner') : null;

  var allInputs = [
    inputName, inputAge, inputBloodGroup, inputPhone, inputLocation,
    selectGender, inputWeight, inputLastDonation, selectAvailability, inputMedicalStatus
  ];

  /**
   * Helper to clear visual validation errors from inputs
   */
  function clearFieldErrors() {
    allInputs.forEach(function (elem) {
      if (elem) elem.classList.remove('input-invalid');
    });
  }

  /**
   * Helper to show the error alert box and focus the problematic field
   */
  function showRegistrationError(title, message, focusElement) {
    if (successAlert) successAlert.style.display = 'none';

    if (errorTitle) errorTitle.textContent = title;
    if (errorMessage) errorMessage.textContent = message;
    if (errorAlert) {
      errorAlert.style.display = 'flex';
      errorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    if (focusElement) {
      focusElement.classList.add('input-invalid');
      focusElement.focus();
    }
  }

  /**
   * Helper to show the success alert box
   */
  function showRegistrationSuccess(donorName, donorId) {
    if (errorAlert) errorAlert.style.display = 'none';

    if (successTitle) successTitle.textContent = 'Donor Registered Successfully!';
    if (successMessage) {
      successMessage.textContent = 'Thank you, ' + donorName +
        '! Your registration has been confirmed and saved in the database.';
    }
    if (assignedIdPill) {
      assignedIdPill.textContent = 'Assigned Donor ID: #' + (donorId !== undefined ? donorId : '--');
    }

    if (successAlert) {
      successAlert.style.display = 'flex';
      successAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  /**
   * Set loading button state during asynchronous request
   */
  function setLoadingState(isLoading) {
    if (!submitBtn) return;

    if (isLoading) {
      submitBtn.disabled = true;
      if (btnText) btnText.textContent = 'Registering Donor...';
      if (btnSpinner) btnSpinner.style.display = 'inline-block';
    } else {
      submitBtn.disabled = false;
      if (btnText) btnText.textContent = '🤝 Complete Registration';
      if (btnSpinner) btnSpinner.style.display = 'none';
    }
  }

  // Handle Form Submission
  regForm.addEventListener('submit', function (e) {
    e.preventDefault();

    // Reset previous error indicators
    clearFieldErrors();
    if (errorAlert) errorAlert.style.display = 'none';
    if (successAlert) successAlert.style.display = 'none';

    // Collect and sanitize form values
    var name = inputName ? inputName.value.trim() : '';
    var rawAge = inputAge ? inputAge.value.trim() : '';
    var bloodGroup = inputBloodGroup ? inputBloodGroup.value.trim() : '';
    var phone = inputPhone ? inputPhone.value.trim() : '';
    var location = inputLocation ? inputLocation.value.trim() : '';
    var gender = selectGender ? selectGender.value.trim() : 'Male';
    var rawWeight = inputWeight ? inputWeight.value.trim() : '';
    var lastDonation = inputLastDonation ? inputLastDonation.value.trim() : '';
    var availability = selectAvailability ? (selectAvailability.value === 'true') : true;
    var medicalStatus = inputMedicalStatus ? inputMedicalStatus.value.trim() : 'Healthy';

    // 1. Client-Side Validation: Full Name
    if (!name || name.length < 2) {
      showRegistrationError('Invalid Full Name', 'Please enter your full name (minimum 2 characters).', inputName);
      return;
    }

    // 2. Client-Side Validation: Age (18-65 standard donation criteria)
    if (!rawAge) {
      showRegistrationError('Age Required', 'Please enter your age in years.', inputAge);
      return;
    }
    var age = parseInt(rawAge, 10);
    if (isNaN(age) || age < 18 || age > 65) {
      showRegistrationError('Age Ineligible', 'Donor age must be between 18 and 65 years to donate blood.', inputAge);
      return;
    }

    // 3. Client-Side Validation: Blood Group
    var validBloodGroups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
    if (!bloodGroup || validBloodGroups.indexOf(bloodGroup) === -1) {
      showRegistrationError('Blood Group Required', 'Please select a valid blood group from the list.', inputBloodGroup);
      return;
    }

    // 4. Client-Side Validation: Phone Number (7 to 15 digits)
    var phoneDigits = phone.replace(/[^0-9]/g, '');
    if (!phone || phoneDigits.length < 7 || phone.length > 15) {
      showRegistrationError('Invalid Phone Number', 'Please enter a valid contact phone number (7 to 15 digits).', inputPhone);
      return;
    }

    // 5. Client-Side Validation: Location / City
    if (!location || location.length < 2) {
      showRegistrationError('Location Required', 'Please enter your current city or district.', inputLocation);
      return;
    }

    // 6. Client-Side Validation: Body Weight (if provided)
    var weight = null;
    if (rawWeight) {
      weight = parseFloat(rawWeight);
      if (isNaN(weight) || weight < 40 || weight > 250) {
        showRegistrationError('Invalid Weight', 'Weight must be a valid number between 40 kg and 250 kg.', inputWeight);
        return;
      }
    }

    // Prepare JSON payload matching POST /donors schema
    var payload = {
      name: name,
      age: age,
      gender: gender || null,
      blood_group: bloodGroup,
      phone: phone,
      location: location,
      availability: availability,
      last_donation_date: lastDonation || null,
      weight: weight,
      medical_status: medicalStatus || 'Healthy'
    };

    // Set loading state and prevent repeated clicks
    setLoadingState(true);

    // Send POST request to existing Flask endpoint
    fetch('/donors', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data.error || data.message || ('Server returned HTTP ' + response.status));
          }
          return data;
        }).catch(function (parseErr) {
          if (!response.ok) {
            throw new Error('Server returned HTTP ' + response.status);
          }
          throw parseErr;
        });
      })
      .then(function (data) {
        // Confirmation: show success feedback with assigned ID
        showRegistrationSuccess(name, data.donor_id);

        // Reset the form only after confirmed success
        regForm.reset();
        clearFieldErrors();

        // Restore sensible default values
        if (inputMedicalStatus) inputMedicalStatus.value = 'Healthy';
        if (selectAvailability) selectAvailability.value = 'true';
        if (selectGender) selectGender.value = 'Male';

        // Refresh donor directory if loaded
        if (window.refreshDonorsDirectory) {
          window.refreshDonorsDirectory();
        }

        // Refresh dashboard overview metrics
        if (typeof window.refreshDashboardOverview === 'function') {
          window.refreshDashboardOverview();
        }
      })
      .catch(function (error) {
        // Clear and accessible error notification
        showRegistrationError('Registration Error', error.message || 'An error occurred while saving donor details.');
      })
      .finally(function () {
        // Re-enable form submission
        setLoadingState(false);
      });
  });

  // Handle Form Reset
  regForm.addEventListener('reset', function () {
    clearFieldErrors();
    if (errorAlert) errorAlert.style.display = 'none';
    if (successAlert) successAlert.style.display = 'none';

    // Restore sensible defaults on next tick
    setTimeout(function () {
      if (inputMedicalStatus) inputMedicalStatus.value = 'Healthy';
      if (selectAvailability) selectAvailability.value = 'true';
      if (selectGender) selectGender.value = 'Male';
    }, 0);
  });
}

// ========================================================
// Module 2b: Donor Management & Availability Directory
// ========================================================
function initDonorManagement() {
  var container = document.getElementById('donor-management');
  if (!container || container.style.display === 'none' || !window.currentUser || window.currentUser.role !== 'ADMIN') return;

  var filterInput = document.getElementById('donor-mgmt-filter-input');
  var availFilter = document.getElementById('donor-mgmt-avail-filter');
  var countBadge = document.getElementById('donor-mgmt-count-badge');
  var refreshBtn = document.getElementById('btn-refresh-donors');

  var mgmtAlert = document.getElementById('donor-mgmt-alert');
  var mgmtAlertTitle = document.getElementById('donor-mgmt-alert-title');
  var mgmtAlertMsg = document.getElementById('donor-mgmt-alert-message');

  var loadingState = document.getElementById('donors-mgmt-loading');
  var errorState = document.getElementById('donors-mgmt-error');
  var errorMsg = document.getElementById('donors-mgmt-error-msg');
  var emptyState = document.getElementById('donors-mgmt-empty');
  var emptyMsg = document.getElementById('donors-mgmt-empty-msg');
  var grid = document.getElementById('donors-mgmt-grid');

  // Modal elements
  var modal = document.getElementById('donor-edit-modal');
  var modalCloseBtn = document.getElementById('btn-close-modal');
  var modalCancelBtn = document.getElementById('btn-cancel-edit');
  var modalForm = document.getElementById('donor-edit-form');
  var modalErrorAlert = document.getElementById('modal-error-alert');
  var modalErrorTitle = document.getElementById('modal-error-title');
  var modalErrorMsg = document.getElementById('modal-error-message');
  var saveBtn = document.getElementById('btn-save-donor');
  var saveBtnText = saveBtn ? saveBtn.querySelector('.btn-text') : null;
  var saveBtnSpinner = saveBtn ? saveBtn.querySelector('.btn-spinner') : null;

  // Modal Form Inputs
  var editDonorId = document.getElementById('edit-donor-id');
  var editName = document.getElementById('edit-name');
  var editAge = document.getElementById('edit-age');
  var editBloodGroup = document.getElementById('edit-blood-group');
  var editPhone = document.getElementById('edit-phone');
  var editLocation = document.getElementById('edit-location');
  var editGender = document.getElementById('edit-gender');
  var editWeight = document.getElementById('edit-weight');
  var editLastDonation = document.getElementById('edit-last-donation');
  var editAvailability = document.getElementById('edit-availability');
  var editMedicalStatus = document.getElementById('edit-medical-status');

  var allDonors = [];

  function showMgmtAlert(isSuccess, title, message) {
    if (!mgmtAlert) return;
    mgmtAlert.className = 'registration-alert ' + (isSuccess ? 'alert-success' : 'alert-error');
    var icon = mgmtAlert.querySelector('.alert-icon');
    if (icon) icon.textContent = isSuccess ? '✅' : '⚠️';
    if (mgmtAlertTitle) mgmtAlertTitle.textContent = title;
    if (mgmtAlertMsg) mgmtAlertMsg.textContent = message;
    mgmtAlert.style.display = 'flex';
    mgmtAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function setViewState(state) {
    if (loadingState) loadingState.style.display = (state === 'loading') ? 'block' : 'none';
    if (errorState) errorState.style.display = (state === 'error') ? 'flex' : 'none';
    if (emptyState) emptyState.style.display = (state === 'empty') ? 'block' : 'none';
    if (grid) grid.style.display = (state === 'content') ? 'grid' : 'none';
  }

  function formatDateForInput(dateVal) {
    if (!dateVal) return '';
    var d = new Date(dateVal);
    if (isNaN(d.getTime())) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(String(dateVal))) return String(dateVal);
      return '';
    }
    var year = d.getFullYear();
    var month = ('0' + (d.getMonth() + 1)).slice(-2);
    var day = ('0' + d.getDate()).slice(-2);
    return year + '-' + month + '-' + day;
  }

  function formatDisplayDate(dateVal) {
    if (!dateVal) return 'First-time / No prior record';
    var d = new Date(dateVal);
    if (isNaN(d.getTime())) return String(dateVal);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function loadDonors() {
    if (!window.currentUser || window.currentUser.role !== 'ADMIN') {
      return;
    }
    setViewState('loading');

    fetch('/donors')
      .then(function (res) {
        if (!res.ok) throw new Error('Server returned HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        allDonors = Array.isArray(data) ? data : [];
        filterAndRenderDonors();
      })
      .catch(function (err) {
        setViewState('error');
        if (errorMsg) {
          errorMsg.textContent = 'Could not load donor directory: ' + err.message;
        }
      });
  }

  function filterAndRenderDonors() {
    if (!grid) return;

    var query = filterInput ? filterInput.value.trim().toLowerCase() : '';
    var availChoice = availFilter ? availFilter.value : 'ALL';

    var filtered = allDonors.filter(function (d) {
      // Availability filter
      if (availChoice === 'AVAILABLE' && d.availability !== 1) return false;
      if (availChoice === 'UNAVAILABLE' && d.availability === 1) return false;

      // Text search query
      if (query) {
        var nameMatch = (d.name || '').toLowerCase().indexOf(query) !== -1;
        var bloodMatch = (d.blood_group || '').toLowerCase().indexOf(query) !== -1;
        var locMatch = (d.location || '').toLowerCase().indexOf(query) !== -1;
        var phoneMatch = (d.phone || '').indexOf(query) !== -1;
        if (!nameMatch && !bloodMatch && !locMatch && !phoneMatch) return false;
      }
      return true;
    });

    if (countBadge) {
      countBadge.textContent = filtered.length + (filtered.length === 1 ? ' Donor' : ' Donors');
    }

    if (filtered.length === 0) {
      setViewState('empty');
      if (emptyMsg) {
        emptyMsg.textContent = query
          ? 'No registered donors found matching "' + query + '".'
          : 'No registered donors match the selected availability filter.';
      }
      return;
    }

    while (grid.firstChild) {
      grid.removeChild(grid.firstChild);
    }

    filtered.forEach(function (donor) {
      var isAvailable = (donor.availability === 1);
      var card = document.createElement('div');
      card.className = 'donor-mgmt-card' + (isAvailable ? '' : ' donor-inactive');

      // Top Row: Blood group badge & availability status badge
      var cardTop = document.createElement('div');
      cardTop.className = 'donor-card-top';

      var bloodBadge = document.createElement('div');
      bloodBadge.className = 'donor-blood-badge';
      bloodBadge.textContent = donor.blood_group || 'N/A';

      var availBadge = document.createElement('span');
      availBadge.className = 'availability-badge ' + (isAvailable ? 'avail-active' : 'avail-inactive');
      availBadge.textContent = isAvailable ? '● Available to Donate' : '○ Currently Unavailable';
      availBadge.title = isAvailable ? 'Self-reported available for urgent requests' : 'Currently resting / unavailable';

      cardTop.appendChild(bloodBadge);
      cardTop.appendChild(availBadge);
      card.appendChild(cardTop);

      // Donor Name & ID
      var cardName = document.createElement('h4');
      cardName.className = 'donor-card-name';
      cardName.textContent = donor.name || 'Anonymous Donor';
      card.appendChild(cardName);

      var idBadge = document.createElement('div');
      idBadge.className = 'donor-id-pill';
      idBadge.textContent = 'Donor ID: #' + donor.donor_id;
      card.appendChild(idBadge);

      // Details List
      var detailsList = document.createElement('ul');
      detailsList.className = 'donor-details-list';

      // Age & Gender
      var ageItem = document.createElement('li');
      var ageLabel = document.createElement('span');
      ageLabel.className = 'detail-label';
      ageLabel.textContent = 'Profile:';
      var ageVal = document.createElement('span');
      ageVal.className = 'detail-value';
      ageVal.textContent = donor.age + ' yrs' + (donor.gender ? ' • ' + donor.gender : '');
      ageItem.appendChild(ageLabel);
      ageItem.appendChild(ageVal);
      detailsList.appendChild(ageItem);

      // Phone
      var phoneItem = document.createElement('li');
      var phoneLabel = document.createElement('span');
      phoneLabel.className = 'detail-label';
      phoneLabel.textContent = 'Contact:';
      var phoneVal = document.createElement('span');
      phoneVal.className = 'detail-value';
      phoneVal.textContent = donor.phone || 'N/A';
      phoneItem.appendChild(phoneLabel);
      phoneItem.appendChild(phoneVal);
      detailsList.appendChild(phoneItem);

      // Location
      var locItem = document.createElement('li');
      var locLabel = document.createElement('span');
      locLabel.className = 'detail-label';
      locLabel.textContent = 'Location:';
      var locVal = document.createElement('span');
      locVal.className = 'detail-value';
      locVal.textContent = donor.location || 'Not Specified';
      locItem.appendChild(locLabel);
      locItem.appendChild(locVal);
      detailsList.appendChild(locItem);

      // Weight
      if (donor.weight) {
        var wtItem = document.createElement('li');
        var wtLabel = document.createElement('span');
        wtLabel.className = 'detail-label';
        wtLabel.textContent = 'Weight:';
        var wtVal = document.createElement('span');
        wtVal.className = 'detail-value';
        wtVal.textContent = donor.weight + ' kg';
        wtItem.appendChild(wtLabel);
        wtItem.appendChild(wtVal);
        detailsList.appendChild(wtItem);
      }

      // Last Donation
      var lastItem = document.createElement('li');
      var lastLabel = document.createElement('span');
      lastLabel.className = 'detail-label';
      lastLabel.textContent = 'Last Donated:';
      var lastVal = document.createElement('span');
      lastVal.className = 'detail-value';
      lastVal.textContent = formatDisplayDate(donor.last_donation_date);
      lastItem.appendChild(lastLabel);
      lastItem.appendChild(lastVal);
      detailsList.appendChild(lastItem);

      // Health status note
      if (donor.medical_status) {
        var medItem = document.createElement('li');
        var medLabel = document.createElement('span');
        medLabel.className = 'detail-label';
        medLabel.textContent = 'Health Note:';
        var medVal = document.createElement('span');
        medVal.className = 'detail-value';
        medVal.textContent = donor.medical_status;
        medItem.appendChild(medLabel);
        medItem.appendChild(medVal);
        detailsList.appendChild(medItem);
      }

      card.appendChild(detailsList);

      // Actions Row: Edit Details & Toggle Availability
      var actionsRow = document.createElement('div');
      actionsRow.className = 'donor-card-actions';

      // 1. Edit Button
      var editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'btn-card-action btn-action-edit';
      editBtn.textContent = '✏️ Edit Profile';
      editBtn.title = 'Edit contact details, location, and medical status for ' + donor.name;
      editBtn.addEventListener('click', function () {
        openEditModal(donor);
      });

      // 2. Availability Toggle Button
      var toggleBtn = document.createElement('button');
      toggleBtn.type = 'button';
      toggleBtn.className = 'btn-card-action btn-action-toggle ' + (isAvailable ? 'toggle-to-off' : 'toggle-to-on');
      toggleBtn.textContent = isAvailable ? '⏸️ Mark Unavailable' : '▶️ Mark Available';
      toggleBtn.title = isAvailable
        ? 'Set status to unavailable (resting). This will exclude the donor from new search matches.'
        : 'Set status to available. This will include the donor in compatible search matches.';
      toggleBtn.addEventListener('click', function () {
        handleToggleAvailability(donor, toggleBtn);
      });

      actionsRow.appendChild(editBtn);
      actionsRow.appendChild(toggleBtn);
      card.appendChild(actionsRow);

      grid.appendChild(card);
    });

    setViewState('content');
  }

  // Handle Availability Toggle with User Confirmation
  function handleToggleAvailability(donor, button) {
    var isCurrentlyAvailable = (donor.availability === 1);
    var targetAvail = isCurrentlyAvailable ? 0 : 1;
    var targetText = isCurrentlyAvailable ? 'UNAVAILABLE (On Rest)' : 'AVAILABLE to Donate';

    var confirmMsg = 'Are you sure you want to change donation availability for ' + donor.name + ' to ' + targetText + '?\n\n' +
      (isCurrentlyAvailable
        ? 'This will exclude ' + donor.name + ' from compatible search matches.\n\n(Note: Availability indicates voluntary readiness and does not guarantee medical clearance.)'
        : 'This will include ' + donor.name + ' in compatible search matches.\n\n(Note: Availability indicates voluntary readiness and does not guarantee medical clearance.)');

    if (!window.confirm(confirmMsg)) {
      return;
    }

    if (button) {
      button.disabled = true;
      button.textContent = 'Updating...';
    }

    fetch('/donors/' + donor.donor_id + '/availability', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        availability: targetAvail
      })
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.error || ('Server returned HTTP ' + res.status));
          return data;
        }).catch(function (parseErr) {
          if (!res.ok) throw new Error('Server returned HTTP ' + res.status);
          throw parseErr;
        });
      })
      .then(function (data) {
        showMgmtAlert(
          true,
          'Availability Updated',
          'Donor #' + donor.donor_id + ' (' + donor.name + ') has been marked as ' +
            (targetAvail === 1 ? 'AVAILABLE' : 'UNAVAILABLE') + '.'
        );
        loadDonors();
        if (typeof window.refreshDashboardOverview === 'function') {
          window.refreshDashboardOverview();
        }
      })
      .catch(function (err) {
        showMgmtAlert(
          false,
          'Update Failed',
          err.message || 'Could not update donor availability. Please try again.'
        );
        if (button) {
          button.disabled = false;
          button.textContent = isCurrentlyAvailable ? '⏸️ Mark Unavailable' : '▶️ Mark Available';
        }
      });
  }

  // Modal Management
  function showModalError(title, message) {
    if (!modalErrorAlert) return;
    if (modalErrorTitle) modalErrorTitle.textContent = title;
    if (modalErrorMsg) modalErrorMsg.textContent = message;
    modalErrorAlert.style.display = 'flex';
  }

  function hideModalError() {
    if (modalErrorAlert) modalErrorAlert.style.display = 'none';
  }

  function openEditModal(donor) {
    if (!modal) return;
    hideModalError();

    if (editDonorId) editDonorId.value = donor.donor_id;
    if (editName) editName.value = donor.name || '';
    if (editAge) editAge.value = donor.age || '';
    if (editBloodGroup) editBloodGroup.value = donor.blood_group || 'A+';
    if (editPhone) editPhone.value = donor.phone || '';
    if (editLocation) editLocation.value = donor.location || '';
    if (editGender) editGender.value = donor.gender || 'Male';
    if (editWeight) editWeight.value = (donor.weight !== null && donor.weight !== undefined) ? donor.weight : '';
    if (editLastDonation) editLastDonation.value = formatDateForInput(donor.last_donation_date);
    if (editAvailability) editAvailability.value = (donor.availability === 1) ? 'true' : 'false';
    if (editMedicalStatus) editMedicalStatus.value = donor.medical_status || 'Healthy';

    modal.style.display = 'flex';
    if (editName) editName.focus();
  }

  function closeEditModal() {
    if (modal) modal.style.display = 'none';
    hideModalError();
  }

  // Modal Listeners
  if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeEditModal);
  if (modalCancelBtn) modalCancelBtn.addEventListener('click', closeEditModal);

  // Close modal when clicking backdrop
  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeEditModal();
    });
  }

  // Close on Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal && modal.style.display !== 'none') {
      closeEditModal();
    }
  });

  // Modal Form Submission (PUT /donors/<donor_id>)
  if (modalForm) {
    modalForm.addEventListener('submit', function (e) {
      e.preventDefault();
      hideModalError();

      var donorId = editDonorId ? editDonorId.value : null;
      if (!donorId) {
        showModalError('Invalid Donor', 'No donor ID found for editing.');
        return;
      }

      var name = editName ? editName.value.trim() : '';
      var rawAge = editAge ? editAge.value.trim() : '';
      var bloodGroup = editBloodGroup ? editBloodGroup.value.trim() : '';
      var phone = editPhone ? editPhone.value.trim() : '';
      var location = editLocation ? editLocation.value.trim() : '';
      var gender = editGender ? editGender.value.trim() : 'Male';
      var rawWeight = editWeight ? editWeight.value.trim() : '';
      var lastDonation = editLastDonation ? editLastDonation.value.trim() : '';
      var availability = editAvailability ? (editAvailability.value === 'true') : true;
      var medicalStatus = editMedicalStatus ? editMedicalStatus.value.trim() : 'Healthy';

      // Validation
      if (!name || name.length < 2) {
        showModalError('Invalid Name', 'Full name must be at least 2 characters.');
        if (editName) editName.focus();
        return;
      }

      var age = parseInt(rawAge, 10);
      if (isNaN(age) || age < 18 || age > 65) {
        showModalError('Invalid Age', 'Donor age must be between 18 and 65 years.');
        if (editAge) editAge.focus();
        return;
      }

      var validBloodGroups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
      if (!bloodGroup || validBloodGroups.indexOf(bloodGroup) === -1) {
        showModalError('Invalid Blood Group', 'Please select a valid blood group.');
        if (editBloodGroup) editBloodGroup.focus();
        return;
      }

      var phoneDigits = phone.replace(/[^0-9]/g, '');
      if (!phone || phoneDigits.length < 7 || phone.length > 15) {
        showModalError('Invalid Phone', 'Phone number must be between 7 and 15 digits.');
        if (editPhone) editPhone.focus();
        return;
      }

      if (!location || location.length < 2) {
        showModalError('Invalid Location', 'Location/City must be at least 2 characters.');
        if (editLocation) editLocation.focus();
        return;
      }

      var weight = null;
      if (rawWeight) {
        weight = parseFloat(rawWeight);
        if (isNaN(weight) || weight < 40 || weight > 250) {
          showModalError('Invalid Weight', 'Weight must be between 40 kg and 250 kg.');
          if (editWeight) editWeight.focus();
          return;
        }
      }

      var payload = {
        name: name,
        age: age,
        gender: gender || null,
        blood_group: bloodGroup,
        phone: phone,
        location: location,
        availability: availability,
        last_donation_date: lastDonation || null,
        weight: weight,
        medical_status: medicalStatus || 'Healthy'
      };

      if (saveBtn) saveBtn.disabled = true;
      if (saveBtnText) saveBtnText.textContent = 'Saving Changes...';
      if (saveBtnSpinner) saveBtnSpinner.style.display = 'inline-block';

      fetch('/donors/' + donorId, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) throw new Error(data.error || ('Server returned HTTP ' + res.status));
            return data;
          }).catch(function (parseErr) {
            if (!res.ok) throw new Error('Server returned HTTP ' + res.status);
            throw parseErr;
          });
        })
        .then(function (data) {
          closeEditModal();
          showMgmtAlert(
            true,
            'Profile Saved Successfully',
            'Details for donor #' + donorId + ' (' + name + ') have been updated in the database.'
          );
          loadDonors();
          if (typeof window.refreshDashboardOverview === 'function') {
            window.refreshDashboardOverview();
          }
        })
        .catch(function (err) {
          showModalError('Save Failed', err.message || 'An error occurred while saving donor details.');
        })
        .finally(function () {
          if (saveBtn) saveBtn.disabled = false;
          if (saveBtnText) saveBtnText.textContent = '💾 Save Changes';
          if (saveBtnSpinner) saveBtnSpinner.style.display = 'none';
        });
    });
  }

  // Toolbar Listeners
  if (filterInput) {
    filterInput.addEventListener('input', function () {
      filterAndRenderDonors();
    });
  }

  if (availFilter) {
    availFilter.addEventListener('change', function () {
      filterAndRenderDonors();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      loadDonors();
    });
  }

  // Global refresh hook for donor registration
  window.refreshDonorsDirectory = function () {
    loadDonors();
  };

  // Initial load
  loadDonors();
}

// ========================================================
// Module 3: Emergency Requests & Live Board
// ========================================================
function initEmergencyRequests() {
  var emergencyForm = document.getElementById('emergency-request-form');
  var refreshBtn = document.getElementById('btn-refresh-emergency');
  var cardsContainer = document.getElementById('emergency-cards-container');
  var countBadge = document.getElementById('emergency-count-badge');

  var feedLoading = document.getElementById('emergency-feed-loading');
  var feedError = document.getElementById('emergency-feed-error');
  var feedErrorMsg = document.getElementById('emergency-feed-error-msg');
  var feedEmpty = document.getElementById('emergency-feed-empty');

  // Archive Feed Elements
  var archiveCardsContainer = document.getElementById('archive-cards-container');
  var archiveCountBadge = document.getElementById('emergency-archive-count-badge');
  var archiveFeedLoading = document.getElementById('archive-feed-loading');
  var archiveFeedError = document.getElementById('archive-feed-error');
  var archiveFeedErrorMsg = document.getElementById('archive-feed-error-msg');
  var archiveFeedEmpty = document.getElementById('archive-feed-empty');
  var refreshArchiveBtn = document.getElementById('btn-refresh-archive');

  // Status Update Feedback Alert
  var updateAlert = document.getElementById('emergency-update-alert');
  var updateAlertTitle = document.getElementById('emergency-update-title');
  var updateAlertMessage = document.getElementById('emergency-update-message');

  var inputBloodGroup = document.getElementById('emg-blood-group');
  var inputUnits = document.getElementById('emg-units');
  var selectLevel = document.getElementById('emg-level');
  var selectHospital = document.getElementById('emg-hospital');
  var selectRecipient = document.getElementById('emg-recipient');

  var successAlert = document.getElementById('emergency-success');
  var successTitle = document.getElementById('emergency-success-title');
  var successMessage = document.getElementById('emergency-success-message');
  var assignedIdPill = document.getElementById('assigned-emergency-id');

  var errorAlert = document.getElementById('emergency-error');
  var errorTitle = document.getElementById('emergency-error-title');
  var errorMessage = document.getElementById('emergency-error-message');

  var submitBtn = document.getElementById('btn-submit-emergency');
  var btnText = submitBtn ? submitBtn.querySelector('.btn-text') : null;
  var btnSpinner = submitBtn ? submitBtn.querySelector('.btn-spinner') : null;

  var hospitalsCache = {};
  var recipientsCache = {};

  var formInputs = [inputBloodGroup, inputUnits, selectLevel, selectHospital, selectRecipient];

  function clearFormErrors() {
    formInputs.forEach(function (el) {
      if (el) el.classList.remove('input-invalid');
    });
  }

  function showEmergencyError(title, message, focusElement) {
    if (successAlert) successAlert.style.display = 'none';
    if (errorTitle) errorTitle.textContent = title;
    if (errorMessage) errorMessage.textContent = message;
    if (errorAlert) {
      errorAlert.style.display = 'flex';
      errorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    if (focusElement) {
      focusElement.classList.add('input-invalid');
      focusElement.focus();
    }
  }

  function showEmergencySuccess(requestId) {
    if (errorAlert) errorAlert.style.display = 'none';
    if (successTitle) successTitle.textContent = 'Emergency Request Broadcasted!';
    if (successMessage) {
      successMessage.textContent = 'Your urgent request has been broadcasted to the emergency board.';
    }
    if (assignedIdPill) {
      assignedIdPill.textContent = 'Request ID: #' + (requestId !== undefined ? requestId : '--');
    }
    if (successAlert) {
      successAlert.style.display = 'flex';
      successAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function showStatusUpdateAlert(isSuccess, title, message) {
    if (!updateAlert) return;
    updateAlert.className = 'registration-alert ' + (isSuccess ? 'alert-success' : 'alert-error');
    var iconEl = updateAlert.querySelector('.alert-icon');
    if (iconEl) iconEl.textContent = isSuccess ? '✅' : '⚠️';
    if (updateAlertTitle) updateAlertTitle.textContent = title;
    if (updateAlertMessage) updateAlertMessage.textContent = message;
    updateAlert.style.display = 'flex';
    updateAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function setSubmittingState(isSubmitting) {
    if (!submitBtn) return;
    if (isSubmitting) {
      submitBtn.disabled = true;
      if (btnText) btnText.textContent = 'Broadcasting Emergency...';
      if (btnSpinner) btnSpinner.style.display = 'inline-block';
    } else {
      submitBtn.disabled = false;
      if (btnText) btnText.textContent = '🚨 Broadcast Emergency Request';
      if (btnSpinner) btnSpinner.style.display = 'none';
    }
  }

  function setFeedState(state) {
    if (feedLoading) feedLoading.style.display = (state === 'loading') ? 'block' : 'none';
    if (feedError) feedError.style.display = (state === 'error') ? 'flex' : 'none';
    if (feedEmpty) feedEmpty.style.display = (state === 'empty') ? 'block' : 'none';
    if (cardsContainer) cardsContainer.style.display = (state === 'content') ? 'grid' : 'none';
  }

  function setArchiveState(state) {
    if (archiveFeedLoading) archiveFeedLoading.style.display = (state === 'loading') ? 'block' : 'none';
    if (archiveFeedError) archiveFeedError.style.display = (state === 'error') ? 'flex' : 'none';
    if (archiveFeedEmpty) archiveFeedEmpty.style.display = (state === 'empty') ? 'block' : 'none';
    if (archiveCardsContainer) archiveCardsContainer.style.display = (state === 'content') ? 'grid' : 'none';
  }

  // Load Hospitals from /hospitals
  function loadHospitals() {
    if (!window.currentUser || !window.currentUser.isAuthenticated) {
      if (selectHospital) {
        selectHospital.innerHTML = '<option value="">-- Login required to link hospital --</option>';
      }
      return;
    }
    fetch('/hospitals')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (hospitals) {
        if (!selectHospital) return;
        selectHospital.innerHTML = '';

        var defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = 'Select hospital (Optional)...';
        selectHospital.appendChild(defaultOpt);

        hospitals.forEach(function (h) {
          hospitalsCache[h.hospital_id] = h;
          var opt = document.createElement('option');
          opt.value = h.hospital_id;
          opt.textContent = h.hospital_name + ' (' + (h.city || '') + ')';
          selectHospital.appendChild(opt);
        });

        renderCurrentFeed();
        renderArchivedFeed();
      })
      .catch(function () {
        if (selectHospital) {
          selectHospital.innerHTML = '<option value="">Hospital list unavailable</option>';
        }
      });
  }

  // Load Recipients from /recipients
  function loadRecipients() {
    if (!window.currentUser || window.currentUser.role !== 'ADMIN') {
      if (selectRecipient) {
        selectRecipient.innerHTML = '<option value="">-- Direct Emergency / Patient Record --</option>';
      }
      return;
    }
    fetch('/recipients')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (recipients) {
        if (!selectRecipient) return;
        selectRecipient.innerHTML = '';

        var defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = '-- No specific patient record / Direct Emergency --';
        selectRecipient.appendChild(defaultOpt);

        recipients.forEach(function (r) {
          recipientsCache[r.recipient_id] = r;
          var opt = document.createElement('option');
          opt.value = r.recipient_id;
          opt.textContent = 'Patient #' + r.recipient_id + ': ' + r.name + ' (' + r.blood_group + ', ' + r.location + ')';
          selectRecipient.appendChild(opt);
        });

        renderCurrentFeed();
        renderArchivedFeed();
      })
      .catch(function () {
        if (selectRecipient) {
          selectRecipient.innerHTML = '<option value="">Recipient list unavailable</option>';
        }
      });
  }

  window.refreshEmergencyRecipientsDropdown = loadRecipients;

  // Auto-fill blood group when recipient is selected
  if (selectRecipient) {
    selectRecipient.addEventListener('change', function () {
      var recipientId = selectRecipient.value;
      if (recipientId && recipientsCache[recipientId]) {
        var rec = recipientsCache[recipientId];
        if (rec.blood_group && inputBloodGroup) {
          inputBloodGroup.value = rec.blood_group;
        }
        if (rec.units_required && inputUnits) {
          inputUnits.value = rec.units_required;
        }
        if (rec.hospital_id && selectHospital) {
          selectHospital.value = rec.hospital_id;
        }
        if (rec.emergency_level && selectLevel) {
          selectLevel.value = rec.emergency_level;
        }
      }
    });
  }

  var currentRequestsList = [];
  var archivedRequestsList = [];

  // ========================================================
  // Status Update Handler (with confirmation prompt)
  // ========================================================
  function handleStatusUpdate(requestId, targetStatus, triggerButton) {
    var isFulfill = (targetStatus === 'FULFILLED');
    var confirmMessage = isFulfill
      ? 'Are you sure you want to resolve Emergency Request #' + requestId + ' as FULFILLED?\n\nThis will remove it from the active urgent board and archive it.'
      : 'Are you sure you want to CANCEL Emergency Request #' + requestId + '?\n\nThis will remove it from the active urgent board and mark it as cancelled.';

    // Ask for explicit confirmation before changing status
    if (!window.confirm(confirmMessage)) {
      return;
    }

    if (triggerButton) {
      triggerButton.disabled = true;
      triggerButton.textContent = 'Updating...';
    }

    fetch('/emergency/' + requestId + '/status', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        status: targetStatus
      })
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) {
            throw new Error(data.error || ('Server returned HTTP ' + res.status));
          }
          return data;
        }).catch(function (err) {
          if (!res.ok) {
            throw new Error('Server returned HTTP ' + res.status);
          }
          throw err;
        });
      })
      .then(function (data) {
        showStatusUpdateAlert(
          true,
          'Emergency Request Updated',
          'Emergency Request #' + requestId + ' was successfully marked as ' + targetStatus + '.'
        );

        // Refresh both the active board and archive feed
        loadEmergencyRequests();
        loadArchivedRequests();
        if (typeof window.refreshDashboardOverview === 'function') {
          window.refreshDashboardOverview();
        }
      })
      .catch(function (err) {
        showStatusUpdateAlert(
          false,
          'Status Update Failed',
          err.message || 'Failed to update emergency request status. Please try again.'
        );
        if (triggerButton) {
          triggerButton.disabled = false;
          triggerButton.textContent = isFulfill ? '✅ Mark as Fulfilled' : '❌ Cancel Request';
        }
      });
  }

  // Load Active Emergency Requests from /emergency (defaults to request_status='ACTIVE')
  function loadEmergencyRequests() {
    if (!window.currentUser || !window.currentUser.isAuthenticated) {
      setFeedState('empty');
      if (feedEmpty) {
        feedEmpty.innerHTML = '<div class="empty-icon">🔐</div><h3>Authentication Required</h3><p>Please <a href="/login" style="color:var(--accent-red);font-weight:600;">log in</a> or <a href="/signup" style="color:var(--accent-red);font-weight:600;">sign up</a> to view and interact with real-time emergency requests.</p>';
      }
      return;
    }
    setFeedState('loading');

    fetch('/emergency')
      .then(function (res) {
        if (!res.ok) throw new Error('Server returned HTTP ' + res.status);
        return res.json();
      })
      .then(function (requests) {
        currentRequestsList = requests || [];
        renderCurrentFeed();
      })
      .catch(function (err) {
        setFeedState('error');
        if (feedErrorMsg) {
          feedErrorMsg.textContent = 'Could not load emergency requests: ' + err.message;
        }
      });
  }

  // Render Active Emergency Requests
  function renderCurrentFeed() {
    if (!cardsContainer) return;

    if (!currentRequestsList || currentRequestsList.length === 0) {
      if (countBadge) countBadge.textContent = '0 Active';
      setFeedState('empty');
      return;
    }

    if (countBadge) {
      countBadge.textContent = currentRequestsList.length +
        (currentRequestsList.length === 1 ? ' Active Request' : ' Active Requests');
    }

    // Safely clear old cards
    while (cardsContainer.firstChild) {
      cardsContainer.removeChild(cardsContainer.firstChild);
    }

    currentRequestsList.forEach(function (req) {
      var card = document.createElement('div');
      card.className = 'emergency-request-card';

      // Card top
      var cardTop = document.createElement('div');
      cardTop.className = 'donor-card-top';

      var bloodBadge = document.createElement('div');
      bloodBadge.className = 'donor-blood-badge';
      bloodBadge.textContent = req.blood_group_required || 'N/A';

      var topMeta = document.createElement('div');
      topMeta.style.display = 'flex';
      topMeta.style.flexDirection = 'column';
      topMeta.style.alignItems = 'flex-end';
      topMeta.style.gap = '0.35rem';

      var priorityPill = document.createElement('span');
      var level = (req.emergency_level || 'NORMAL').toUpperCase();
      priorityPill.className = 'priority-pill priority-' + level;

      if (level === 'CRITICAL') {
        var dot = document.createElement('span');
        dot.className = 'pulse-dot';
        priorityPill.appendChild(dot);
      }
      var levelText = document.createTextNode(' ' + level);
      priorityPill.appendChild(levelText);

      var unitsBadge = document.createElement('span');
      unitsBadge.className = 'units-badge';
      unitsBadge.textContent = (req.units_required || 1) + ' Units Needed';

      topMeta.appendChild(priorityPill);
      topMeta.appendChild(unitsBadge);

      cardTop.appendChild(bloodBadge);
      cardTop.appendChild(topMeta);
      card.appendChild(cardTop);

      // Request Title & ID
      var cardTitle = document.createElement('h4');
      cardTitle.className = 'donor-card-name';
      cardTitle.textContent = 'Emergency Request #' + req.request_id;
      card.appendChild(cardTitle);

      // Display Status Clearly
      var statusBadge = document.createElement('div');
      statusBadge.style.margin = '0.4rem 0';
      var statusPill = document.createElement('span');
      statusPill.className = 'status-pill status-ACTIVE';
      statusPill.textContent = '● ACTIVE';
      statusBadge.appendChild(statusPill);
      card.appendChild(statusBadge);

      // Details List
      var detailsList = document.createElement('ul');
      detailsList.className = 'donor-details-list';

      // Hospital
      var hospItem = document.createElement('li');
      var hospLabel = document.createElement('span');
      hospLabel.className = 'detail-label';
      hospLabel.textContent = 'Hospital:';
      var hospValue = document.createElement('span');
      hospValue.className = 'detail-value';

      if (req.hospital_id && hospitalsCache[req.hospital_id]) {
        var hObj = hospitalsCache[req.hospital_id];
        hospValue.textContent = hObj.hospital_name + ' (' + (hObj.city || '') + ')';
      } else if (req.hospital_id) {
        hospValue.textContent = 'Hospital ID #' + req.hospital_id;
      } else {
        hospValue.textContent = 'Unspecified / Field emergency';
      }
      hospItem.appendChild(hospLabel);
      hospItem.appendChild(hospValue);
      detailsList.appendChild(hospItem);

      // Recipient / Patient
      var recItem = document.createElement('li');
      var recLabel = document.createElement('span');
      recLabel.className = 'detail-label';
      recLabel.textContent = 'Patient:';
      var recValue = document.createElement('span');
      recValue.className = 'detail-value';

      if (req.recipient_id && recipientsCache[req.recipient_id]) {
        recValue.textContent = recipientsCache[req.recipient_id].name;
      } else if (req.recipient_id) {
        recValue.textContent = 'Recipient ID #' + req.recipient_id;
      } else {
        recValue.textContent = 'Direct Emergency Broadcast';
      }
      recItem.appendChild(recLabel);
      recItem.appendChild(recValue);
      detailsList.appendChild(recItem);

      // Date / Time
      if (req.request_date) {
        var dateItem = document.createElement('li');
        var dateLabel = document.createElement('span');
        dateLabel.className = 'detail-label';
        dateLabel.textContent = 'Posted:';
        var dateValue = document.createElement('span');
        dateValue.className = 'detail-value';
        dateValue.textContent = req.request_date;
        dateItem.appendChild(dateLabel);
        dateItem.appendChild(dateValue);
        detailsList.appendChild(dateItem);
      }

      card.appendChild(detailsList);

      // Quick Action: Match Donors Button (preserves existing feature)
      var matchBtn = document.createElement('button');
      matchBtn.type = 'button';
      matchBtn.className = 'btn-card-match';
      matchBtn.textContent = '🔍 Find Matching Donors for ' + (req.blood_group_required || 'this');
      matchBtn.addEventListener('click', function () {
        var searchSection = document.getElementById('find-donors');
        var searchSelect = document.getElementById('search-blood-group');
        var searchLoc = document.getElementById('search-location');
        var searchBtn = document.getElementById('btn-submit-search');

        if (searchSelect && req.blood_group_required) {
          searchSelect.value = req.blood_group_required;
        }

        if (searchLoc) {
          if (req.hospital_id && hospitalsCache[req.hospital_id]) {
            searchLoc.value = hospitalsCache[req.hospital_id].city || '';
          } else if (req.recipient_id && recipientsCache[req.recipient_id]) {
            searchLoc.value = recipientsCache[req.recipient_id].location || '';
          }
        }

        if (searchSection) {
          searchSection.scrollIntoView({ behavior: 'smooth' });
        }

        if (searchBtn) {
          setTimeout(function () {
            searchBtn.click();
          }, 400);
        }
      });
      card.appendChild(matchBtn);

      // Actions Row: Show actions for resolving or cancelling active requests
      var actionsRow = document.createElement('div');
      actionsRow.className = 'emergency-card-actions';

      var fulfillBtn = document.createElement('button');
      fulfillBtn.type = 'button';
      fulfillBtn.className = 'btn-card-action btn-action-fulfill';
      fulfillBtn.textContent = '✅ Mark as Fulfilled';
      fulfillBtn.title = 'Resolve this emergency request as fulfilled';
      fulfillBtn.addEventListener('click', function () {
        handleStatusUpdate(req.request_id, 'FULFILLED', fulfillBtn);
      });

      var cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'btn-card-action btn-action-cancel';
      cancelBtn.textContent = '❌ Cancel Request';
      cancelBtn.title = 'Cancel this emergency request';
      cancelBtn.addEventListener('click', function () {
        handleStatusUpdate(req.request_id, 'CANCELLED', cancelBtn);
      });

      actionsRow.appendChild(fulfillBtn);
      actionsRow.appendChild(cancelBtn);
      card.appendChild(actionsRow);

      cardsContainer.appendChild(card);
    });

    setFeedState('content');
  }

  // ========================================================
  // Archive Feed (Resolved & Cancelled Requests)
  // ========================================================
  function loadArchivedRequests() {
    if (!archiveCardsContainer) return;
    if (!window.currentUser || !window.currentUser.isAuthenticated) {
      setArchiveState('empty');
      if (archiveFeedEmpty) {
        archiveFeedEmpty.innerHTML = '<div class="empty-icon">🔐</div><h3>Authentication Required</h3><p>Please <a href="/login" style="color:var(--accent-red);font-weight:600;">log in</a> to view archived emergency requests.</p>';
      }
      return;
    }
    setArchiveState('loading');

    fetch('/emergency?status=history')
      .then(function (res) {
        if (!res.ok) throw new Error('Server returned HTTP ' + res.status);
        return res.json();
      })
      .then(function (requests) {
        archivedRequestsList = requests || [];
        renderArchivedFeed();
      })
      .catch(function (err) {
        setArchiveState('error');
        if (archiveFeedErrorMsg) {
          archiveFeedErrorMsg.textContent = 'Could not load archive: ' + err.message;
        }
      });
  }

  function renderArchivedFeed() {
    if (!archiveCardsContainer) return;

    if (!archivedRequestsList || archivedRequestsList.length === 0) {
      if (archiveCountBadge) archiveCountBadge.textContent = '0 Closed';
      setArchiveState('empty');
      return;
    }

    if (archiveCountBadge) {
      archiveCountBadge.textContent = archivedRequestsList.length +
        (archivedRequestsList.length === 1 ? ' Closed Request' : ' Closed Requests');
    }

    while (archiveCardsContainer.firstChild) {
      archiveCardsContainer.removeChild(archiveCardsContainer.firstChild);
    }

    archivedRequestsList.forEach(function (req) {
      var card = document.createElement('div');
      var statusClass = (req.request_status || '').toLowerCase();
      card.className = 'emergency-request-card card-' + statusClass;

      // Card top
      var cardTop = document.createElement('div');
      cardTop.className = 'donor-card-top';

      var bloodBadge = document.createElement('div');
      bloodBadge.className = 'donor-blood-badge';
      bloodBadge.textContent = req.blood_group_required || 'N/A';

      var topMeta = document.createElement('div');
      topMeta.style.display = 'flex';
      topMeta.style.flexDirection = 'column';
      topMeta.style.alignItems = 'flex-end';
      topMeta.style.gap = '0.35rem';

      var priorityPill = document.createElement('span');
      var level = (req.emergency_level || 'NORMAL').toUpperCase();
      priorityPill.className = 'priority-pill priority-' + level;
      priorityPill.textContent = level;

      var unitsBadge = document.createElement('span');
      unitsBadge.className = 'units-badge';
      unitsBadge.textContent = (req.units_required || 1) + ' Units';

      topMeta.appendChild(priorityPill);
      topMeta.appendChild(unitsBadge);

      cardTop.appendChild(bloodBadge);
      cardTop.appendChild(topMeta);
      card.appendChild(cardTop);

      // Request Title & ID
      var cardTitle = document.createElement('h4');
      cardTitle.className = 'donor-card-name';
      cardTitle.textContent = 'Emergency Request #' + req.request_id;
      card.appendChild(cardTitle);

      // Display Status Clearly (Do NOT show resolve/cancel actions here)
      var statusBadge = document.createElement('div');
      statusBadge.style.margin = '0.4rem 0';
      var statusPill = document.createElement('span');
      var isFulfilled = (req.request_status === 'FULFILLED');
      statusPill.className = 'status-pill status-' + (req.request_status || 'CANCELLED');
      statusPill.textContent = isFulfilled ? '✅ FULFILLED' : '❌ CANCELLED';
      statusBadge.appendChild(statusPill);
      card.appendChild(statusBadge);

      // Details List
      var detailsList = document.createElement('ul');
      detailsList.className = 'donor-details-list';

      // Hospital
      var hospItem = document.createElement('li');
      var hospLabel = document.createElement('span');
      hospLabel.className = 'detail-label';
      hospLabel.textContent = 'Hospital:';
      var hospValue = document.createElement('span');
      hospValue.className = 'detail-value';

      if (req.hospital_id && hospitalsCache[req.hospital_id]) {
        var hObj = hospitalsCache[req.hospital_id];
        hospValue.textContent = hObj.hospital_name + ' (' + (hObj.city || '') + ')';
      } else if (req.hospital_id) {
        hospValue.textContent = 'Hospital ID #' + req.hospital_id;
      } else {
        hospValue.textContent = 'Unspecified';
      }
      hospItem.appendChild(hospLabel);
      hospItem.appendChild(hospValue);
      detailsList.appendChild(hospItem);

      // Patient
      var recItem = document.createElement('li');
      var recLabel = document.createElement('span');
      recLabel.className = 'detail-label';
      recLabel.textContent = 'Patient:';
      var recValue = document.createElement('span');
      recValue.className = 'detail-value';

      if (req.recipient_id && recipientsCache[req.recipient_id]) {
        recValue.textContent = recipientsCache[req.recipient_id].name;
      } else if (req.recipient_id) {
        recValue.textContent = 'Recipient ID #' + req.recipient_id;
      } else {
        recValue.textContent = 'Direct Broadcast';
      }
      recItem.appendChild(recLabel);
      recItem.appendChild(recValue);
      detailsList.appendChild(recItem);

      // Date
      if (req.request_date) {
        var dateItem = document.createElement('li');
        var dateLabel = document.createElement('span');
        dateLabel.className = 'detail-label';
        dateLabel.textContent = 'Posted:';
        var dateValue = document.createElement('span');
        dateValue.className = 'detail-value';
        dateValue.textContent = req.request_date;
        dateItem.appendChild(dateLabel);
        dateItem.appendChild(dateValue);
        detailsList.appendChild(dateItem);
      }

      card.appendChild(detailsList);

      // NOTE: Resolved/Cancelled requests do NOT have resolve or cancel buttons!
      archiveCardsContainer.appendChild(card);
    });

    setArchiveState('content');
  }

  // Handle Emergency Request Form Submit
  if (emergencyForm) {
    emergencyForm.addEventListener('submit', function (e) {
      e.preventDefault();

      clearFormErrors();
      if (errorAlert) errorAlert.style.display = 'none';
      if (successAlert) successAlert.style.display = 'none';

      var bloodGroup = inputBloodGroup ? inputBloodGroup.value.trim() : '';
      var unitsStr = inputUnits ? inputUnits.value.trim() : '';
      var level = selectLevel ? selectLevel.value.trim() : '';
      var hospitalVal = selectHospital ? selectHospital.value.trim() : '';
      var recipientVal = selectRecipient ? selectRecipient.value.trim() : '';

      // Validation
      var validBloodGroups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
      if (!bloodGroup || validBloodGroups.indexOf(bloodGroup) === -1) {
        showEmergencyError('Blood Group Required', 'Please select a required blood group for the emergency.', inputBloodGroup);
        return;
      }

      var units = parseInt(unitsStr, 10);
      if (isNaN(units) || units < 1 || units > 20) {
        showEmergencyError('Invalid Units', 'Please enter a valid number of blood units between 1 and 20.', inputUnits);
        return;
      }

      var validLevels = ['CRITICAL', 'HIGH', 'NORMAL', 'LOW'];
      if (!level || validLevels.indexOf(level) === -1) {
        showEmergencyError('Priority Level Required', 'Please select an emergency priority level.', selectLevel);
        return;
      }

      var hospitalId = hospitalVal ? parseInt(hospitalVal, 10) : null;
      var recipientId = recipientVal ? parseInt(recipientVal, 10) : null;

      var payload = {
        blood_group_required: bloodGroup,
        units_required: units,
        emergency_level: level,
        hospital_id: hospitalId,
        recipient_id: recipientId
      };

      setSubmittingState(true);

      fetch('/emergency', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) {
              throw new Error(data.error || data.message || ('Server error: HTTP ' + res.status));
            }
            return data;
          }).catch(function (parseErr) {
            if (!res.ok) {
              throw new Error('Server returned HTTP ' + res.status);
            }
            throw parseErr;
          });
        })
        .then(function (data) {
          showEmergencySuccess(data.request_id);

          emergencyForm.reset();
          clearFormErrors();

          if (inputUnits) inputUnits.value = '1';
          if (selectLevel) selectLevel.value = 'CRITICAL';

          // Refresh the live feed immediately
          loadEmergencyRequests();
          if (typeof window.refreshDashboardOverview === 'function') {
            window.refreshDashboardOverview();
          }
        })
        .catch(function (err) {
          showEmergencyError('Emergency Submission Failed', err.message || 'An error occurred while submitting the request.');
        })
        .finally(function () {
          setSubmittingState(false);
        });
    });

    // Form Reset
    emergencyForm.addEventListener('reset', function () {
      clearFormErrors();
      if (errorAlert) errorAlert.style.display = 'none';
      if (successAlert) successAlert.style.display = 'none';

      setTimeout(function () {
        if (inputUnits) inputUnits.value = '1';
        if (selectLevel) selectLevel.value = 'CRITICAL';
      }, 0);
    });
  }

  // Refresh Feed Buttons
  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      loadEmergencyRequests();
    });
  }

  if (refreshArchiveBtn) {
    refreshArchiveBtn.addEventListener('click', function () {
      loadArchivedRequests();
    });
  }

  // Initial load
  loadHospitals();
  loadRecipients();
  loadEmergencyRequests();
  loadArchivedRequests();
}

// ========================================================
// Module 5: Live Dashboard Overview & Real-Time Telemetry
// ========================================================
function initDashboardOverview() {
  var totalDonorsEl = document.getElementById('dash-total-donors');
  var availableDonorsEl = document.getElementById('dash-available-donors');
  var activeEmergenciesEl = document.getElementById('dash-active-emergencies');
  var recentCountTagEl = document.getElementById('dash-recent-count-tag');
  var recentLoadingEl = document.getElementById('dash-recent-loading');
  var recentEmptyEl = document.getElementById('dash-recent-empty');
  var recentTableWrapEl = document.getElementById('dash-recent-table-wrap');
  var recentTbodyEl = document.getElementById('dash-recent-tbody');
  var errorStateEl = document.getElementById('dash-error-state');
  var errorMsgEl = document.getElementById('dash-error-msg');
  var lastUpdatedEl = document.getElementById('dash-last-updated');
  var refreshBtn = document.getElementById('btn-refresh-dashboard');

  // If dashboard markup is not present, exit gracefully
  if (!totalDonorsEl && !recentTbodyEl) return;

  /**
   * Safe date formatting helper for dashboard table
   */
  function formatDashboardDate(dateVal) {
    if (!dateVal) return 'N/A';
    try {
      var d = new Date(dateVal);
      if (isNaN(d.getTime())) {
        d = new Date(String(dateVal).replace(' ', 'T'));
      }
      if (isNaN(d.getTime())) return String(dateVal);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    } catch (e) {
      return String(dateVal);
    }
  }

  /**
   * Render recent emergency requests into table rows
   */
  function renderRecentRequests(requests) {
    if (!recentTbodyEl) return;

    if (!requests || requests.length === 0) {
      if (recentEmptyEl) recentEmptyEl.style.display = 'block';
      if (recentTableWrapEl) recentTableWrapEl.style.display = 'none';
      if (recentCountTagEl) recentCountTagEl.textContent = '0 Requests';
      recentTbodyEl.innerHTML = '';
      return;
    }

    if (recentEmptyEl) recentEmptyEl.style.display = 'none';
    if (recentTableWrapEl) recentTableWrapEl.style.display = 'block';
    if (recentCountTagEl) {
      recentCountTagEl.textContent = requests.length + (requests.length === 1 ? ' Recent Request' : ' Recent Requests');
    }

    recentTbodyEl.innerHTML = '';

    requests.forEach(function (req) {
      var tr = document.createElement('tr');

      // Req ID
      var tdId = document.createElement('td');
      var pillId = document.createElement('span');
      pillId.className = 'dash-req-id-pill';
      pillId.textContent = '#' + (req.request_id != null ? req.request_id : '-');
      tdId.appendChild(pillId);
      tr.appendChild(tdId);

      // Blood Group
      var tdGroup = document.createElement('td');
      var pillGroup = document.createElement('span');
      pillGroup.className = 'dash-blood-pill';
      pillGroup.textContent = req.blood_group_required || 'N/A';
      tdGroup.appendChild(pillGroup);
      tr.appendChild(tdGroup);

      // Units
      var tdUnits = document.createElement('td');
      var unitsVal = req.units_required != null ? req.units_required : 1;
      tdUnits.textContent = unitsVal + (unitsVal === 1 ? ' Unit' : ' Units');
      tr.appendChild(tdUnits);

      // Priority Level
      var tdLevel = document.createElement('td');
      var pillLevel = document.createElement('span');
      var level = (req.emergency_level || 'STANDARD').toUpperCase();
      pillLevel.className = 'priority-pill priority-' + level.toLowerCase();
      pillLevel.textContent = level;
      tdLevel.appendChild(pillLevel);
      tr.appendChild(tdLevel);

      // Hospital / Location
      var tdHospital = document.createElement('td');
      var hospName = req.hospital_name || 'Direct Emergency Broadcast';
      if (req.hospital_city) {
        hospName += ' (' + req.hospital_city + ')';
      }
      tdHospital.textContent = hospName;
      tr.appendChild(tdHospital);

      // Status
      var tdStatus = document.createElement('td');
      var pillStatus = document.createElement('span');
      var status = (req.request_status || 'ACTIVE').toUpperCase();
      pillStatus.className = 'status-pill status-' + status.toLowerCase();
      pillStatus.textContent = status;
      tdStatus.appendChild(pillStatus);
      tr.appendChild(tdStatus);

      // Date Posted
      var tdDate = document.createElement('td');
      tdDate.textContent = formatDashboardDate(req.request_date);
      tr.appendChild(tdDate);

      recentTbodyEl.appendChild(tr);
    });
  }

  /**
   * Fetch live dashboard statistics and recent requests from /dashboard/stats
   */
  function loadDashboardOverview() {
    if (errorStateEl) errorStateEl.style.display = 'none';
    if (recentLoadingEl && (!recentTbodyEl || recentTbodyEl.children.length === 0)) {
      recentLoadingEl.style.display = 'block';
    }

    return fetch('/dashboard/stats')
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) {
            throw new Error(data.error || data.message || ('Server returned HTTP ' + res.status));
          }
          return data;
        }).catch(function (parseErr) {
          if (!res.ok) throw new Error('Server returned HTTP ' + res.status);
          throw parseErr;
        });
      })
      .then(function (data) {
        // Update metric counts
        if (totalDonorsEl) {
          totalDonorsEl.textContent = (data.total_donors != null ? data.total_donors : 0);
        }
        if (availableDonorsEl) {
          availableDonorsEl.textContent = (data.available_donors != null ? data.available_donors : 0);
        }
        if (activeEmergenciesEl) {
          activeEmergenciesEl.textContent = (data.active_emergency_requests != null ? data.active_emergency_requests : 0);
        }

        // Render recent emergency requests list
        renderRecentRequests(data.recent_requests || []);

        // Timestamp
        if (lastUpdatedEl) {
          var now = new Date();
          var timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
          lastUpdatedEl.textContent = 'Updated at ' + timeStr;
        }

        return data;
      })
      .catch(function (err) {
        console.error('Failed to load dashboard overview telemetry:', err);
        if (errorStateEl) {
          errorStateEl.style.display = 'flex';
          if (errorMsgEl) {
            errorMsgEl.textContent = err.message || 'Could not load live dashboard telemetry from server.';
          }
        }
      })
      .finally(function () {
        if (recentLoadingEl) recentLoadingEl.style.display = 'none';
        if (refreshBtn) {
          refreshBtn.disabled = false;
          refreshBtn.textContent = '🔄 Refresh Dashboard';
        }
      });
  }

  // Refresh button listener
  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      refreshBtn.disabled = true;
      refreshBtn.textContent = '⏳ Refreshing...';
      loadDashboardOverview();
    });
  }

  // Expose global refresh function so other modules can trigger live updates
  window.refreshDashboardOverview = loadDashboardOverview;

  // Initial load
  loadDashboardOverview();
}

// ========================================================
// Module 6: Recipient Registration (POST /recipients)
// ========================================================
function initRecipientRegistration() {
  var form = document.getElementById('recipient-registration-form');
  if (!form) return;

  var inputName = document.getElementById('rec-name');
  var inputAge = document.getElementById('rec-age');
  var selectBloodGroup = document.getElementById('rec-blood-group');
  var inputPhone = document.getElementById('rec-phone');
  var inputLocation = document.getElementById('rec-location');
  var selectGender = document.getElementById('rec-gender');
  var selectHospital = document.getElementById('rec-hospital');
  var inputUnits = document.getElementById('rec-units');
  var selectLevel = document.getElementById('rec-level');

  var successAlert = document.getElementById('recipient-success');
  var successTitle = document.getElementById('recipient-success-title');
  var successMsg = document.getElementById('recipient-success-message');
  var assignedIdBadge = document.getElementById('assigned-recipient-id');

  var errorAlert = document.getElementById('recipient-error');
  var errorTitle = document.getElementById('recipient-error-title');
  var errorMsg = document.getElementById('recipient-error-message');

  var submitBtn = document.getElementById('btn-submit-recipient');
  var submitBtnText = submitBtn ? submitBtn.querySelector('.btn-text') : null;
  var submitBtnSpinner = submitBtn ? submitBtn.querySelector('.btn-spinner') : null;

  // Load Hospitals into dropdown
  if (selectHospital) {
    if (!window.currentUser || !window.currentUser.isAuthenticated) {
      selectHospital.innerHTML = '<option value="">-- Login required for hospital affiliation --</option>';
    } else {
      fetch('/hospitals')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (hospitals) {
        selectHospital.innerHTML = '';
        var defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = '-- No Specific Hospital / Outpatient --';
        selectHospital.appendChild(defaultOpt);

        hospitals.forEach(function (h) {
          var opt = document.createElement('option');
          opt.value = h.hospital_id;
          opt.textContent = h.hospital_name + ' (' + (h.city || '') + ')';
          selectHospital.appendChild(opt);
        });
      })
      .catch(function () {
        if (selectHospital) {
          selectHospital.innerHTML = '<option value="">Hospital list unavailable</option>';
        }
      });
    }
  }

  function hideAlerts() {
    if (successAlert) successAlert.style.display = 'none';
    if (errorAlert) errorAlert.style.display = 'none';
  }

  function showError(title, message) {
    if (errorAlert) {
      if (errorTitle) errorTitle.textContent = title;
      if (errorMsg) errorMsg.textContent = message;
      errorAlert.style.display = 'flex';
      errorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function showSuccess(recipientId, message) {
    if (successAlert) {
      if (successTitle) successTitle.textContent = 'Recipient Registered Successfully!';
      if (successMsg) successMsg.textContent = message || 'Profile created and ready for transfusion coordination.';
      if (assignedIdBadge) assignedIdBadge.textContent = 'Recipient ID: #' + recipientId;
      successAlert.style.display = 'flex';
      successAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  // Handle Form Submission
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    hideAlerts();

    var name = inputName ? inputName.value.trim() : '';
    var rawAge = inputAge ? inputAge.value.trim() : '';
    var bloodGroup = selectBloodGroup ? selectBloodGroup.value.trim() : '';
    var phone = inputPhone ? inputPhone.value.trim() : '';
    var location = inputLocation ? inputLocation.value.trim() : '';
    var gender = selectGender ? selectGender.value.trim() : '';
    var hospitalId = selectHospital ? selectHospital.value.trim() : '';
    var rawUnits = inputUnits ? inputUnits.value.trim() : '1';
    var emergencyLevel = selectLevel ? selectLevel.value.trim() : 'NORMAL';

    // Client-side Validations
    if (!name || name.length < 2) {
      showError('Validation Error', 'Full name must be at least 2 characters long.');
      if (inputName) inputName.focus();
      return;
    }

    if (!rawAge) {
      showError('Validation Error', 'Age is required.');
      if (inputAge) inputAge.focus();
      return;
    }

    var ageNum = parseInt(rawAge, 10);
    if (isNaN(ageNum) || ageNum < 1 || ageNum > 120) {
      showError('Validation Error', 'Age must be a valid whole number between 1 and 120 years.');
      if (inputAge) inputAge.focus();
      return;
    }

    var validBloodGroups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
    if (!bloodGroup || validBloodGroups.indexOf(bloodGroup.toUpperCase()) === -1) {
      showError('Validation Error', 'Please select a valid blood group (A+, A-, B+, B-, AB+, AB-, O+, O-).');
      if (selectBloodGroup) selectBloodGroup.focus();
      return;
    }

    if (!phone) {
      showError('Validation Error', 'Contact phone number is required.');
      if (inputPhone) inputPhone.focus();
      return;
    }

    var phoneDigits = phone.replace(/\D/g, '');
    if (phoneDigits.length < 7 || phoneDigits.length > 15) {
      showError('Validation Error', 'Phone number must contain between 7 and 15 digits.');
      if (inputPhone) inputPhone.focus();
      return;
    }

    if (!location || location.length < 2) {
      showError('Validation Error', 'Location / City must be at least 2 characters long.');
      if (inputLocation) inputLocation.focus();
      return;
    }

    var unitsNum = 1;
    if (rawUnits) {
      unitsNum = parseInt(rawUnits, 10);
      if (isNaN(unitsNum) || unitsNum < 1 || unitsNum > 20) {
        showError('Validation Error', 'Units required must be a whole number between 1 and 20.');
        if (inputUnits) inputUnits.focus();
        return;
      }
    }

    var validLevels = ['CRITICAL', 'HIGH', 'NORMAL', 'LOW'];
    if (validLevels.indexOf(emergencyLevel.toUpperCase()) === -1) {
      emergencyLevel = 'NORMAL';
    }

    var payload = {
      name: name,
      age: ageNum,
      blood_group: bloodGroup.toUpperCase(),
      phone: phone,
      location: location,
      gender: gender || null,
      hospital_id: hospitalId ? parseInt(hospitalId, 10) : null,
      units_required: unitsNum,
      emergency_level: emergencyLevel.toUpperCase()
    };

    // Button loading state
    if (submitBtn) submitBtn.disabled = true;
    if (submitBtnText) submitBtnText.textContent = 'Registering Profile...';
    if (submitBtnSpinner) submitBtnSpinner.style.display = 'inline-block';

    fetch('/recipients', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (errData) {
            throw new Error(errData.error || ('Server returned HTTP ' + res.status));
          }).catch(function (e) {
            if (e.message && e.message.indexOf('HTTP') === -1) throw e;
            throw new Error('Server returned HTTP ' + res.status);
          });
        }
        return res.json();
      })
      .then(function (data) {
        showSuccess(data.recipient_id, data.message);
        form.reset();
        if (inputUnits) inputUnits.value = '1';
        if (selectLevel) selectLevel.value = 'NORMAL';

        // Refresh Recipient Directory and Emergency Request Dropdowns
        if (typeof window.refreshRecipientsDirectory === 'function') {
          window.refreshRecipientsDirectory();
        }
        if (typeof window.refreshEmergencyRecipientsDropdown === 'function') {
          window.refreshEmergencyRecipientsDropdown();
        }
      })
      .catch(function (err) {
        showError('Registration Failed', err.message || 'Could not register recipient in the database. Please try again.');
      })
      .finally(function () {
        if (submitBtn) submitBtn.disabled = false;
        if (submitBtnText) submitBtnText.textContent = '🏥 Register Recipient Profile';
        if (submitBtnSpinner) submitBtnSpinner.style.display = 'none';
      });
  });

  // Reset button clears alerts too
  form.addEventListener('reset', function () {
    hideAlerts();
    if (inputUnits) setTimeout(function () { inputUnits.value = '1'; }, 10);
    if (selectLevel) setTimeout(function () { selectLevel.value = 'NORMAL'; }, 10);
  });
}

// ========================================================
// Module 7: Recipient Directory & Profile Management
// ========================================================
function initRecipientManagement() {
  var container = document.getElementById('recipient-directory');
  if (!container || container.style.display === 'none' || !window.currentUser || window.currentUser.role !== 'ADMIN') return;

  var searchInput = document.getElementById('recipient-filter-search');
  var bloodFilter = document.getElementById('recipient-filter-blood');
  var locationFilter = document.getElementById('recipient-filter-location');
  var urgencyFilter = document.getElementById('recipient-filter-urgency');
  var countBadge = document.getElementById('recipient-count-badge');
  var resetFiltersBtn = document.getElementById('btn-reset-recipient-filters');
  var refreshBtn = document.getElementById('btn-refresh-recipients');

  var mgmtAlert = document.getElementById('recipient-mgmt-alert');
  var mgmtAlertTitle = document.getElementById('recipient-mgmt-alert-title');
  var mgmtAlertMsg = document.getElementById('recipient-mgmt-alert-message');

  var loadingState = document.getElementById('recipients-loading');
  var errorState = document.getElementById('recipients-error');
  var errorMsg = document.getElementById('recipients-error-msg');
  var emptyState = document.getElementById('recipients-empty');
  var emptyMsg = document.getElementById('recipients-empty-msg');
  var grid = document.getElementById('recipients-grid');

  // Edit Modal Elements
  var modal = document.getElementById('recipient-edit-modal');
  var modalCloseBtn = document.getElementById('btn-close-recipient-modal');
  var modalCancelBtn = document.getElementById('btn-cancel-recipient-edit');
  var modalForm = document.getElementById('recipient-edit-form');
  var modalErrorAlert = document.getElementById('recipient-modal-error-alert');
  var modalErrorTitle = document.getElementById('recipient-modal-error-title');
  var modalErrorMsg = document.getElementById('recipient-modal-error-message');
  var saveBtn = document.getElementById('btn-save-recipient');
  var saveBtnText = saveBtn ? saveBtn.querySelector('.btn-text') : null;
  var saveBtnSpinner = saveBtn ? saveBtn.querySelector('.btn-spinner') : null;

  // Modal Inputs
  var editRecId = document.getElementById('edit-recipient-id');
  var editName = document.getElementById('edit-rec-name');
  var editAge = document.getElementById('edit-rec-age');
  var editBloodGroup = document.getElementById('edit-rec-blood-group');
  var editPhone = document.getElementById('edit-rec-phone');
  var editLocation = document.getElementById('edit-rec-location');
  var editGender = document.getElementById('edit-rec-gender');
  var editHospital = document.getElementById('edit-rec-hospital');
  var editUnits = document.getElementById('edit-rec-units');
  var editLevel = document.getElementById('edit-rec-level');

  var allRecipients = [];
  var hospitalsList = [];

  // Populate Modal Hospitals
  function loadHospitalsForModal() {
    fetch('/hospitals')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (hospitals) {
        hospitalsList = hospitals || [];
        if (!editHospital) return;
        editHospital.innerHTML = '';
        var defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = 'No Hospital Affiliated';
        editHospital.appendChild(defaultOpt);

        hospitalsList.forEach(function (h) {
          var opt = document.createElement('option');
          opt.value = h.hospital_id;
          opt.textContent = h.hospital_name + ' (' + (h.city || '') + ')';
          editHospital.appendChild(opt);
        });
      })
      .catch(function () {});
  }
  loadHospitalsForModal();

  function showMgmtAlert(isSuccess, title, message) {
    if (!mgmtAlert) return;
    mgmtAlert.className = 'registration-alert ' + (isSuccess ? 'alert-success' : 'alert-error');
    var icon = mgmtAlert.querySelector('.alert-icon');
    if (icon) icon.textContent = isSuccess ? '✅' : '⚠️';
    if (mgmtAlertTitle) mgmtAlertTitle.textContent = title;
    if (mgmtAlertMsg) mgmtAlertMsg.textContent = message;
    mgmtAlert.style.display = 'flex';
    mgmtAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function setViewState(state) {
    if (loadingState) loadingState.style.display = (state === 'loading') ? 'block' : 'none';
    if (errorState) errorState.style.display = (state === 'error') ? 'flex' : 'none';
    if (emptyState) emptyState.style.display = (state === 'empty') ? 'block' : 'none';
    if (grid) grid.style.display = (state === 'content') ? 'grid' : 'none';
  }

  function loadRecipients() {
    if (!window.currentUser || window.currentUser.role !== 'ADMIN') {
      return;
    }
    setViewState('loading');

    fetch('/recipients')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        allRecipients = Array.isArray(data) ? data : [];
        applyFiltersAndRender();
      })
      .catch(function (err) {
        setViewState('error');
        if (errorMsg) {
          errorMsg.textContent = err.message || 'Could not load recipient profiles from server.';
        }
      });
  }

  function applyFiltersAndRender() {
    var searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';
    var bloodVal = bloodFilter ? bloodFilter.value.trim().toUpperCase() : '';
    var locVal = locationFilter ? locationFilter.value.trim().toLowerCase() : '';
    var urgencyVal = urgencyFilter ? urgencyFilter.value.trim().toUpperCase() : '';

    var filtered = allRecipients.filter(function (r) {
      if (searchVal && (!r.name || r.name.toLowerCase().indexOf(searchVal) === -1)) {
        return false;
      }
      if (bloodVal && r.blood_group !== bloodVal) {
        return false;
      }
      if (locVal && (!r.location || r.location.toLowerCase().indexOf(locVal) === -1)) {
        return false;
      }
      if (urgencyVal && (!r.emergency_level || r.emergency_level.toUpperCase() !== urgencyVal)) {
        return false;
      }
      return true;
    });

    if (countBadge) {
      countBadge.textContent = filtered.length + ' Recipient' + (filtered.length === 1 ? '' : 's');
    }

    if (filtered.length === 0) {
      setViewState('empty');
      if (emptyMsg) {
        if (searchVal || bloodVal || locVal || urgencyVal) {
          emptyMsg.textContent = 'No recipients match the specified filter criteria. Try clearing or relaxing filters.';
        } else {
          emptyMsg.textContent = 'No recipients currently registered. Use the registration form above to enroll a patient.';
        }
      }
      return;
    }

    setViewState('content');
    renderRecipientCards(filtered);
  }

  function renderRecipientCards(recipients) {
    if (!grid) return;
    grid.innerHTML = '';

    recipients.forEach(function (r) {
      var card = document.createElement('div');
      var urgency = (r.emergency_level || 'NORMAL').toUpperCase();
      card.className = 'recipient-mgmt-card urgency-card-' + urgency.toLowerCase();

      // Top row
      var topRow = document.createElement('div');
      topRow.className = 'recipient-card-top';

      var badgesGroup = document.createElement('div');
      badgesGroup.className = 'recipient-badges-group';

      var bloodBadge = document.createElement('span');
      bloodBadge.className = 'blood-badge';
      bloodBadge.textContent = r.blood_group || '--';
      badgesGroup.appendChild(bloodBadge);

      var urgencyPill = document.createElement('span');
      urgencyPill.className = 'urgency-level-pill urgency-level-' + urgency.toLowerCase();
      var urgencyIcon = (urgency === 'CRITICAL') ? '🚨 ' : (urgency === 'HIGH') ? '⚠️ ' : (urgency === 'NORMAL') ? 'ℹ️ ' : '📋 ';
      urgencyPill.textContent = urgencyIcon + urgency;
      badgesGroup.appendChild(urgencyPill);

      var unitsPill = document.createElement('span');
      unitsPill.className = 'units-required-pill';
      unitsPill.textContent = '🩸 ' + (r.units_required || 1) + ' Unit' + ((r.units_required || 1) === 1 ? '' : 's');
      badgesGroup.appendChild(unitsPill);

      topRow.appendChild(badgesGroup);

      var idBadge = document.createElement('span');
      idBadge.className = 'recipient-card-id';
      idBadge.textContent = '#' + r.recipient_id;
      topRow.appendChild(idBadge);

      card.appendChild(topRow);

      // Patient Name
      var nameEl = document.createElement('h4');
      nameEl.className = 'recipient-card-title';
      nameEl.textContent = r.name || 'Unnamed Recipient';
      card.appendChild(nameEl);

      // Details List
      var detailsList = document.createElement('div');
      detailsList.className = 'recipient-details-list';

      // Age & Gender
      var demogItem = document.createElement('div');
      demogItem.className = 'recipient-detail-item';
      var demogIcon = document.createElement('span');
      demogIcon.className = 'recipient-detail-icon';
      demogIcon.textContent = '👤';
      demogItem.appendChild(demogIcon);
      var demogText = document.createElement('span');
      demogText.textContent = (r.age ? r.age + ' yrs' : 'Age unspecified') + (r.gender ? ' • ' + r.gender : '');
      demogItem.appendChild(demogText);
      detailsList.appendChild(demogItem);

      // Location
      var locItem = document.createElement('div');
      locItem.className = 'recipient-detail-item';
      var locIcon = document.createElement('span');
      locIcon.className = 'recipient-detail-icon';
      locIcon.textContent = '📍';
      locItem.appendChild(locIcon);
      var locText = document.createElement('span');
      locText.textContent = r.location || 'Location unspecified';
      locItem.appendChild(locText);
      detailsList.appendChild(locItem);

      // Phone
      var phoneItem = document.createElement('div');
      phoneItem.className = 'recipient-detail-item';
      var phoneIcon = document.createElement('span');
      phoneIcon.className = 'recipient-detail-icon';
      phoneIcon.textContent = '📞';
      phoneItem.appendChild(phoneIcon);
      var phoneLink = document.createElement('a');
      phoneLink.href = 'tel:' + (r.phone || '');
      phoneLink.textContent = r.phone || 'No phone provided';
      phoneLink.style.color = 'var(--primary-dark-red)';
      phoneLink.style.fontWeight = '600';
      phoneItem.appendChild(phoneLink);
      detailsList.appendChild(phoneItem);

      // Hospital Affiliation
      if (r.hospital_name || r.hospital_id) {
        var hospItem = document.createElement('div');
        hospItem.className = 'recipient-hospital-badge';
        var hospIcon = document.createElement('span');
        hospIcon.textContent = '🏥';
        hospItem.appendChild(hospIcon);
        var hospText = document.createElement('span');
        hospText.textContent = r.hospital_name ? (r.hospital_name + (r.hospital_city ? ' (' + r.hospital_city + ')' : '')) : ('Hospital ID #' + r.hospital_id);
        hospItem.appendChild(hospText);
        detailsList.appendChild(hospItem);
      }

      card.appendChild(detailsList);

      // Actions Row
      var actionsRow = document.createElement('div');
      actionsRow.className = 'recipient-card-actions';

      // Edit Button
      var editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'btn btn-action-edit';
      editBtn.textContent = '✏️ Edit Profile';
      editBtn.addEventListener('click', function () {
        openEditModal(r);
      });
      actionsRow.appendChild(editBtn);

      // Request Blood Quick-Action Button
      var requestBtn = document.createElement('button');
      requestBtn.type = 'button';
      requestBtn.className = 'btn btn-action-broadcast-emergency';
      requestBtn.textContent = '🚨 Request Blood';
      requestBtn.addEventListener('click', function () {
        // Link to emergency form
        var emgSec = document.getElementById('emergency-requests');
        var emgRecipient = document.getElementById('emg-recipient');
        var emgBlood = document.getElementById('emg-blood-group');
        var emgUnits = document.getElementById('emg-units');
        var emgLevel = document.getElementById('emg-level');
        var emgHospital = document.getElementById('emg-hospital');

        if (emgRecipient) {
          emgRecipient.value = r.recipient_id;
        }
        if (emgBlood && r.blood_group) {
          emgBlood.value = r.blood_group;
        }
        if (emgUnits && r.units_required) {
          emgUnits.value = r.units_required;
        }
        if (emgLevel && r.emergency_level) {
          emgLevel.value = r.emergency_level.toUpperCase();
        }
        if (emgHospital && r.hospital_id) {
          emgHospital.value = r.hospital_id;
        }
        if (emgSec) {
          emgSec.scrollIntoView({ behavior: 'smooth' });
        }
      });
      actionsRow.appendChild(requestBtn);

      card.appendChild(actionsRow);
      grid.appendChild(card);
    });
  }

  // Edit Modal Functions
  function openEditModal(recipient) {
    if (!modal) return;
    if (modalErrorAlert) modalErrorAlert.style.display = 'none';

    if (editRecId) editRecId.value = recipient.recipient_id;
    if (editName) editName.value = recipient.name || '';
    if (editAge) editAge.value = recipient.age || '';
    if (editBloodGroup) editBloodGroup.value = recipient.blood_group || 'O+';
    if (editPhone) editPhone.value = recipient.phone || '';
    if (editLocation) editLocation.value = recipient.location || '';
    if (editGender) editGender.value = recipient.gender || '';
    if (editHospital) editHospital.value = recipient.hospital_id || '';
    if (editUnits) editUnits.value = recipient.units_required || 1;
    if (editLevel) editLevel.value = (recipient.emergency_level || 'NORMAL').toUpperCase();

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    if (editName) editName.focus();
  }

  function closeEditModal() {
    if (!modal) return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }

  if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeEditModal);
  if (modalCancelBtn) modalCancelBtn.addEventListener('click', closeEditModal);

  // Close modal when clicking outside
  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeEditModal();
    });
  }

  // Close modal with Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal && modal.style.display === 'flex') {
      closeEditModal();
    }
  });

  // Modal Form Submission
  if (modalForm) {
    modalForm.addEventListener('submit', function (e) {
      e.preventDefault();
      if (modalErrorAlert) modalErrorAlert.style.display = 'none';

      var recipientId = editRecId ? parseInt(editRecId.value, 10) : 0;
      if (!recipientId || recipientId <= 0) {
        showModalError('Invalid recipient ID');
        return;
      }

      var name = editName ? editName.value.trim() : '';
      var rawAge = editAge ? editAge.value.trim() : '';
      var bloodGroup = editBloodGroup ? editBloodGroup.value.trim() : '';
      var phone = editPhone ? editPhone.value.trim() : '';
      var location = editLocation ? editLocation.value.trim() : '';
      var gender = editGender ? editGender.value.trim() : '';
      var hospitalId = editHospital ? editHospital.value.trim() : '';
      var rawUnits = editUnits ? editUnits.value.trim() : '1';
      var emergencyLevel = editLevel ? editLevel.value.trim() : 'NORMAL';

      // Validation
      if (!name || name.length < 2) {
        showModalError('Full name must be at least 2 characters long.');
        if (editName) editName.focus();
        return;
      }

      var ageNum = parseInt(rawAge, 10);
      if (isNaN(ageNum) || ageNum < 1 || ageNum > 120) {
        showModalError('Age must be a valid whole number between 1 and 120 years.');
        if (editAge) editAge.focus();
        return;
      }

      var validBloodGroups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
      if (!bloodGroup || validBloodGroups.indexOf(bloodGroup.toUpperCase()) === -1) {
        showModalError('Please select a valid blood group.');
        if (editBloodGroup) editBloodGroup.focus();
        return;
      }

      var phoneDigits = phone.replace(/\D/g, '');
      if (phoneDigits.length < 7 || phoneDigits.length > 15) {
        showModalError('Phone number must contain between 7 and 15 digits.');
        if (editPhone) editPhone.focus();
        return;
      }

      if (!location || location.length < 2) {
        showModalError('Location / City must be at least 2 characters long.');
        if (editLocation) editLocation.focus();
        return;
      }

      var unitsNum = parseInt(rawUnits, 10);
      if (isNaN(unitsNum) || unitsNum < 1 || unitsNum > 20) {
        showModalError('Units required must be between 1 and 20.');
        if (editUnits) editUnits.focus();
        return;
      }

      var payload = {
        name: name,
        age: ageNum,
        blood_group: bloodGroup.toUpperCase(),
        phone: phone,
        location: location,
        gender: gender || null,
        hospital_id: hospitalId ? parseInt(hospitalId, 10) : null,
        units_required: unitsNum,
        emergency_level: emergencyLevel.toUpperCase()
      };

      if (saveBtn) saveBtn.disabled = true;
      if (saveBtnText) saveBtnText.textContent = 'Saving Changes...';
      if (saveBtnSpinner) saveBtnSpinner.style.display = 'inline-block';

      fetch('/recipients/' + recipientId, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
        .then(function (res) {
          if (!res.ok) {
            return res.json().then(function (errData) {
              throw new Error(errData.error || ('Server returned HTTP ' + res.status));
            }).catch(function (e) {
              if (e.message && e.message.indexOf('HTTP') === -1) throw e;
              throw new Error('Server returned HTTP ' + res.status);
            });
          }
          return res.json();
        })
        .then(function (data) {
          closeEditModal();
          showMgmtAlert(true, 'Recipient Profile Updated', 'Details for recipient #' + recipientId + ' (' + name + ') were saved successfully.');
          loadRecipients();

          if (typeof window.refreshEmergencyRecipientsDropdown === 'function') {
            window.refreshEmergencyRecipientsDropdown();
          }
        })
        .catch(function (err) {
          showModalError(err.message || 'Failed to update recipient details in database.');
        })
        .finally(function () {
          if (saveBtn) saveBtn.disabled = false;
          if (saveBtnText) saveBtnText.textContent = '💾 Save Recipient Changes';
          if (saveBtnSpinner) saveBtnSpinner.style.display = 'none';
        });
    });
  }

  function showModalError(msg) {
    if (modalErrorAlert) {
      if (modalErrorTitle) modalErrorTitle.textContent = 'Update Failed';
      if (modalErrorMsg) modalErrorMsg.textContent = msg;
      modalErrorAlert.style.display = 'flex';
    }
  }

  // Filter Listeners
  if (searchInput) {
    searchInput.addEventListener('input', applyFiltersAndRender);
  }
  if (bloodFilter) {
    bloodFilter.addEventListener('change', applyFiltersAndRender);
  }
  if (locationFilter) {
    locationFilter.addEventListener('input', applyFiltersAndRender);
  }
  if (urgencyFilter) {
    urgencyFilter.addEventListener('change', applyFiltersAndRender);
  }

  if (resetFiltersBtn) {
    resetFiltersBtn.addEventListener('click', function () {
      if (searchInput) searchInput.value = '';
      if (bloodFilter) bloodFilter.value = '';
      if (locationFilter) locationFilter.value = '';
      if (urgencyFilter) urgencyFilter.value = '';
      applyFiltersAndRender();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      refreshBtn.disabled = true;
      refreshBtn.textContent = '⏳ Refreshing...';
      loadRecipients();
      setTimeout(function () {
        refreshBtn.disabled = false;
        refreshBtn.textContent = '🔄 Refresh Directory';
      }, 500);
    });
  }

  // Expose global refresh function
  window.refreshRecipientsDirectory = loadRecipients;

  // Initial directory fetch
  loadRecipients();
}

