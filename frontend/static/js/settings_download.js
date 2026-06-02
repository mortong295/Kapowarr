function fillSettings(api_key) {
	fetchAPI('/settings', api_key)
	.then(json => {
		document.querySelector('#download-folder-input').value = json.result.download_folder;
		document.querySelector('#concurrent-direct-downloads-input').value = json.result.concurrent_direct_downloads;
		document.querySelector('#download-timeout-input').value = ((json.result.failing_download_timeout || 0) / 60) || '';
		document.querySelector('#seeding-handling-input').value = json.result.seeding_handling;
		document.querySelector('#delete-downloads-input').checked = json.result.delete_completed_downloads;
		document.querySelector('#sabnzbd-category-input').value = json.result.sabnzbd_category;
		document.querySelector('#sabnzbd-priority-input').value = json.result.sabnzbd_priority;
		document.querySelector('#sabnzbd-ssl-verify-input').checked = json.result.sabnzbd_use_ssl_verify;
		document.querySelector('#sabnzbd-timeout-input').value = json.result.sabnzbd_timeout_seconds;
		document.querySelector('#sabnzbd-completed-root-input').value = json.result.sabnzbd_completed_download_root;
		document.querySelector('#prowlarr-enabled-input').checked = json.result.prowlarr_enabled;
		document.querySelector('#prowlarr-base-url-input').value = json.result.prowlarr_base_url;
		document.querySelector('#prowlarr-api-key-input').value = json.result.prowlarr_api_key;
		document.querySelector('#prowlarr-timeout-input').value = json.result.prowlarr_timeout_seconds;
		document.querySelector('#prowlarr-categories-input').value = (json.result.prowlarr_comic_categories || []).join(',');
		document.querySelector('#prowlarr-min-seeders-input').value = json.result.prowlarr_minimum_seeders;
		document.querySelector('#prowlarr-prefer-usenet-input').checked = json.result.prowlarr_prefer_usenet;
		fillPref(json.result.service_preference);
	});
};

function saveSettings(api_key) {
	document.querySelector("#save-button p").innerText = 'Saving';
	document.querySelector('#download-folder-input').classList.remove('error-input');
	const data = {
		'download_folder': document.querySelector('#download-folder-input').value,
		'concurrent_direct_downloads': parseInt(document.querySelector('#concurrent-direct-downloads-input').value),
		'failing_download_timeout': parseInt(document.querySelector('#download-timeout-input').value || 0) * 60,
		'seeding_handling': document.querySelector('#seeding-handling-input').value,
		'delete_completed_downloads': document.querySelector('#delete-downloads-input').checked,
		'sabnzbd_category': document.querySelector('#sabnzbd-category-input').value,
		'sabnzbd_priority': document.querySelector('#sabnzbd-priority-input').value,
		'sabnzbd_use_ssl_verify': document.querySelector('#sabnzbd-ssl-verify-input').checked,
		'sabnzbd_timeout_seconds': parseInt(document.querySelector('#sabnzbd-timeout-input').value),
		'sabnzbd_completed_download_root': document.querySelector('#sabnzbd-completed-root-input').value,
		'prowlarr_enabled': document.querySelector('#prowlarr-enabled-input').checked,
		'prowlarr_base_url': document.querySelector('#prowlarr-base-url-input').value,
		'prowlarr_api_key': document.querySelector('#prowlarr-api-key-input').value,
		'prowlarr_timeout_seconds': parseInt(document.querySelector('#prowlarr-timeout-input').value),
		'prowlarr_comic_categories': document.querySelector('#prowlarr-categories-input').value.split(',').map(e => e.trim()).filter(e => e),
		'prowlarr_minimum_seeders': parseInt(document.querySelector('#prowlarr-min-seeders-input').value || 0),
		'prowlarr_prefer_usenet': document.querySelector('#prowlarr-prefer-usenet-input').checked,
		'service_preference': [...document.querySelectorAll('#pref-table select')].map(e => e.value)
	};
	sendAPI('PUT', '/settings', api_key, {}, data)
	.then(response => 
		document.querySelector("#save-button p").innerText = 'Saved'
	)
	.catch(e => {
		document.querySelector("#save-button p").innerText = 'Failed';
        e.json().then(e => {
            if (
                e.error === "InvalidKeyValue"
                && e.result.key === "download_folder"
                ||
                e.error === "FolderNotFound"
            )
                document.querySelector('#download-folder-input').classList.add('error-input');

			else
                console.log(e);
        });
	});
};

//
// Empty download folder
//
function emptyFolder(api_key) {
	sendAPI('DELETE', '/activity/folder', api_key)
	.then(response => {
		document.querySelector('#empty-download-folder').innerText = 'Done';
	});
};

//
// Service preference
//
function fillPref(pref) {
	const selects = document.querySelectorAll('#pref-table select');
	for (let i = 0; i < pref.length; i++) {
		const service = pref[i];
		const select = selects[i];
		select.onchange = updatePrefOrder;
		pref.forEach(option => {
			const entry = document.createElement('option');
			entry.value = option;
			entry.innerText = option.charAt(0).toUpperCase() + option.slice(1);
			if (option === service)
				entry.selected = true;
			select.appendChild(entry);
		});
	};
};

function updatePrefOrder(e) {
	const other_selects = document.querySelectorAll(
		`#pref-table select:not([data-place="${e.target.dataset.place}"])`
	);
	// Find select that has the value of the target select
	for (let i = 0; i < other_selects.length; i++) {
		if (other_selects[i].value === e.target.value) {
			// Set it to old value of target select
			all_values = [...document.querySelector('#pref-table select').options].map(e => e.value)
			used_values = new Set([...document.querySelectorAll('#pref-table select')].map(s => s.value));
			open_value = all_values.filter(e => !used_values.has(e))[0];
			other_selects[i].value = open_value;
			break;
		};
	};
};

// code run on load
usingApiKey()
.then(api_key => {
	fillSettings(api_key);

	document.querySelector('#save-button').onclick = e => saveSettings(api_key);
	document.querySelector('#empty-download-folder').onclick = e => emptyFolder(api_key);
});
