function createUsernameInput(id) {
	const username_row = document.createElement('tr');
	const username_header = document.createElement('th');
	const username_label = document.createElement('label');
	username_label.innerText = 'Username';
	username_label.setAttribute('for', id);
	username_header.appendChild(username_label);
	username_row.appendChild(username_header)
	const username_container = document.createElement('td');
	const username_input = document.createElement('input');
	username_input.type = 'text'
	username_input.id = id;
	username_container.appendChild(username_input);
	username_row.appendChild(username_container);
	return username_row;
};

function createPasswordInput(id) {
	const password_row = document.createElement('tr');
	const password_header = document.createElement('th');
	const password_label = document.createElement('label');
	password_label.innerText = 'Password';
	password_label.setAttribute('for', id);
	password_header.appendChild(password_label);
	password_row.appendChild(password_header)
	const password_container = document.createElement('td');
	const password_input = document.createElement('input');
	password_input.type = 'password'
	password_input.id = id;
	password_container.appendChild(password_input);
	password_row.appendChild(password_container);
	return password_row;
};

function createApiTokenInput(id) {
	const token_row = document.createElement('tr');
	const token_header = document.createElement('th');
	const token_label = document.createElement('label');
	token_label.innerText = 'API Token';
	token_label.setAttribute('for', id);
	token_header.appendChild(token_label);
	token_row.appendChild(token_header)
	const token_container = document.createElement('td');
	const token_input = document.createElement('input');
	token_input.type = 'text'
	token_input.id = id;
	token_container.appendChild(token_input);
	token_row.appendChild(token_container);
	return token_row;
};

function createCheckboxInput(id, label, checked) {
	const row = document.createElement('tr');
	row.classList.add('sabnzbd-setting-row');

	const header = document.createElement('th');
	const label_el = document.createElement('label');
	label_el.innerText = label;
	label_el.setAttribute('for', id);
	header.appendChild(label_el);
	row.appendChild(header);

	const container = document.createElement('td');
	const input = document.createElement('input');
	input.type = 'checkbox';
	input.id = id;
	input.checked = checked;
	container.appendChild(input);
	row.appendChild(container);

	return row;
};

function createTextInput(id, label, value, type='text', help='') {
	const row = document.createElement('tr');
	row.classList.add('sabnzbd-setting-row');

	const header = document.createElement('th');
	const label_el = document.createElement('label');
	label_el.innerText = label;
	label_el.setAttribute('for', id);
	header.appendChild(label_el);
	row.appendChild(header);

	const container = document.createElement('td');
	const input = document.createElement('input');
	input.type = type;
	input.id = id;
	input.value = value || '';
	container.appendChild(input);

	if (help) {
		const description = document.createElement('p');
		description.innerText = help;
		container.appendChild(description);
	};

	row.appendChild(container);
	return row;
};

function createPriorityInput(id, value) {
	const row = document.createElement('tr');
	row.classList.add('sabnzbd-setting-row');

	const header = document.createElement('th');
	const label = document.createElement('label');
	label.innerText = 'Priority';
	label.setAttribute('for', id);
	header.appendChild(label);
	row.appendChild(header);

	const container = document.createElement('td');
	const select = document.createElement('select');
	select.id = id;
	['default', 'paused', 'low', 'normal', 'high', 'force'].forEach(option => {
		const entry = document.createElement('option');
		entry.value = option;
		entry.innerText = option.charAt(0).toUpperCase() + option.slice(1);
		if (option === value)
			entry.selected = true;
		select.appendChild(entry);
	});
	container.appendChild(select);

	const description = document.createElement('p');
	description.innerText = 'Priority assigned to NZBs sent to SABnzbd.';
	container.appendChild(description);

	row.appendChild(container);
	return row;
};

function appendSabnzbdSettings(form, settings) {
	const prefix = form.id.startsWith('add-') ? 'add' : 'edit';
	form.appendChild(createCheckboxInput(
		`${prefix}-sabnzbd-enabled-input`,
		'Enabled',
		settings.sabnzbd_enabled ?? true
	));
	form.appendChild(createTextInput(
		`${prefix}-sabnzbd-category-input`,
		'Category',
		settings.sabnzbd_category || 'comics',
		'text',
		'Category assigned to NZBs sent to SABnzbd.'
	));
	form.appendChild(createPriorityInput(
		`${prefix}-sabnzbd-priority-input`,
		settings.sabnzbd_priority || 'normal'
	));
	form.appendChild(createCheckboxInput(
		`${prefix}-sabnzbd-ssl-verify-input`,
		'Verify SSL',
		settings.sabnzbd_use_ssl_verify ?? true
	));
	form.appendChild(createTextInput(
		`${prefix}-sabnzbd-timeout-input`,
		'Timeout',
		settings.sabnzbd_timeout_seconds || 30,
		'number',
		'Time in seconds before SABnzbd requests time out.'
	));
	form.appendChild(createTextInput(
		`${prefix}-sabnzbd-completed-root-input`,
		'Completed Root',
		settings.sabnzbd_completed_download_root || '',
		'text',
		'Optional fallback folder used when SABnzbd history does not include a completed path.'
	));
};

function getSabnzbdSettingsFromForm(form) {
	const prefix = form.id.startsWith('add-') ? 'add' : 'edit';
	return {
		sabnzbd_enabled: form.querySelector(`#${prefix}-sabnzbd-enabled-input`).checked,
		sabnzbd_category: form.querySelector(`#${prefix}-sabnzbd-category-input`).value,
		sabnzbd_priority: form.querySelector(`#${prefix}-sabnzbd-priority-input`).value,
		sabnzbd_use_ssl_verify: form.querySelector(`#${prefix}-sabnzbd-ssl-verify-input`).checked,
		sabnzbd_timeout_seconds: parseInt(form.querySelector(`#${prefix}-sabnzbd-timeout-input`).value || 30),
		sabnzbd_completed_download_root: form.querySelector(`#${prefix}-sabnzbd-completed-root-input`).value
	};
};

function isSabnzbdForm(form) {
	return form.dataset.type === 'SABnzbd';
};

function isUsenetClient(client) {
	return client.client_type === 'SABnzbd' || client.download_type === 3;
};

function loadEditTorrent(api_key, id) {
	const form = document.querySelector('#edit-torrent-form tbody');
	form.dataset.id = id;
	form.querySelectorAll('.sabnzbd-setting-row').forEach(el => el.remove());
	form.querySelectorAll(
		'tr:not(:has(input#edit-title-input, input#edit-baseurl-input))'
	).forEach(el => el.remove());
	document.querySelector('#test-torrent-edit').classList.remove(
		'show-success', 'show-fail'
	)
	hide([document.querySelector('#edit-error')]);

	fetchAPI(`/externalclients/${id}`, api_key)
	.then(client_data => {
		const client_type = client_data.result.client_type;
		form.dataset.type = client_type;
		fetchAPI('/externalclients/options', api_key)
		.then(options => {
			const client_options = options.result[client_type];

			form.querySelector('#edit-title-input').value =
				client_data.result.title || '';

			form.querySelector('#edit-baseurl-input').value =
				client_data.result.base_url;

			if (client_options.includes('username')) {
				const username_input = createUsernameInput('edit-username-input');
				username_input.querySelector('input').value =
					client_data.result.username || '';
				form.appendChild(username_input);
			};

			if (client_options.includes('password')) {
				const password_input = createPasswordInput('edit-password-input');
				password_input.querySelector('input').value =
					client_data.result.password || '';
				form.appendChild(password_input);
			};

			if (client_options.includes('api_token')) {
				const token_input = createApiTokenInput('edit-token-input');
				token_input.querySelector('input').value =
					client_data.result.api_token || '';
				form.appendChild(token_input);
			};

			if (client_type === 'SABnzbd') {
				fetchAPI('/settings', api_key)
				.then(settings => {
					appendSabnzbdSettings(form, settings.result);
					showWindow('edit-torrent-window');
				});
			} else {
				showWindow('edit-torrent-window');
			};
		});
	});
};

function saveEditTorrent() {
	usingApiKey()
	.then(api_key => {
		testEditTorrent(api_key).then(result => {
			if (!result)
				return;

			const form = document.querySelector('#edit-torrent-form tbody');
			const id = form.dataset.id;
			const data = {
				title: form.querySelector('#edit-title-input').value,
				base_url: form.querySelector('#edit-baseurl-input').value,
				username: form.querySelector('#edit-username-input')?.value || null,
				password: form.querySelector('#edit-password-input')?.value || null,
				api_token: form.querySelector('#edit-token-input')?.value || null
			};
			sendAPI('PUT', `/externalclients/${id}`, api_key, {}, data)
			.then(response => {
				if (isSabnzbdForm(form))
					return sendAPI(
						'PUT',
						'/settings',
						api_key,
						{},
						getSabnzbdSettingsFromForm(form)
					);
			})
			.then(response => {
				loadTorrentClients(api_key);
				fillRemoteMappings(api_key);
				closeWindow();
			})
			.catch(e => {
				e.json().then(json => {
					const error = document.querySelector('#edit-error');
					if (json.error === "ExternalClientDownloading") {
						// Client is downloading
						error.innerText = '*Client is downloading';
						hide([], [error]);

					} else if (
						json.error === "InvalidKeyValue"
						&& json.result.key === "password"
					) {
						error.innerText = "*Username given but no password";
						hide([], [error]);
					};
				});
			});
		});
	});
};

async function testEditTorrent(api_key) {
	const error = document.querySelector('#edit-error');
	hide([error]);
	const form = document.querySelector('#edit-torrent-form tbody');
	const test_button = document.querySelector('#test-torrent-edit');
	test_button.classList.remove('show-success', 'show-fail');
	const data = {
		id: parseInt(form.dataset.id),
		client_type: form.dataset.type,
		base_url: form.querySelector('#edit-baseurl-input').value,
		username: form.querySelector('#edit-username-input')?.value || null,
		password: form.querySelector('#edit-password-input')?.value || null,
		api_token: form.querySelector('#edit-token-input')?.value || null,
	};
	return await sendAPI('POST', '/externalclients/test', api_key, {}, data)
	.then(response => response.json())
	.then(json => {
		if (json.result.success)
			// Test successful
			test_button.classList.add('show-success');
		else {
			// Test failed
			test_button.classList.add('show-fail');
			error.innerText = json.result.description;
			hide([], [error]);
		};
		return json.result.success;
	});
};

function deleteTorrent(api_key) {
	const id = document.querySelector('#edit-torrent-form tbody').dataset.id;
	sendAPI('DELETE', `/externalclients/${id}`, api_key)
	.then(response => {
		loadTorrentClients(api_key);
		fillRemoteMappings(api_key);
		closeWindow();
	})
	.catch(e => {
		if (e.status === 400) {
			// Client is downloading
			const error = document.querySelector('#edit-error');
			error.innerText = '*Client is downloading';
			hide([], [error]);
		};
	});
};

function loadTorrentList(api_key) {
	const usenet_list = document.querySelector('#choose-usenet-list');
	const torrent_list = document.querySelector('#choose-torrent-list');
	usenet_list.innerHTML = '';
	torrent_list.innerHTML = '';

	fetchAPI('/externalclients/options', api_key)
	.then(json => {
		Object.keys(json.result).forEach(c => {
			const entry = document.createElement('button');
			entry.innerText = c;
			entry.onclick = e => loadAddTorrent(api_key, c);
			if (c === 'SABnzbd')
				usenet_list.appendChild(entry);
			else
				torrent_list.appendChild(entry);
		});
		showWindow('choose-torrent-window');
	});
};

function loadAddTorrent(api_key, client_type) {
	const form = document.querySelector('#add-torrent-form tbody');
	form.dataset.type = client_type;
	form.querySelectorAll('.sabnzbd-setting-row').forEach(el => el.remove());
	form.querySelectorAll(
		'tr:not(:has(input#add-title-input, input#add-baseurl-input))'
	).forEach(el => el.remove());
	document.querySelector('#test-torrent-add').classList.remove(
		'show-success', 'show-fail'
	)
	form.querySelectorAll(
		'#add-title-input, #add-baseurl-input'
	).forEach(el => el.value = '');
	form.querySelector('#add-title-input').value = client_type;

	fetchAPI('/externalclients/options', api_key)
	.then(json => {
		const client_options = json.result[client_type];

		if (client_options.includes('username'))
			form.appendChild(createUsernameInput('add-username-input'));

		if (client_options.includes('password'))
			form.appendChild(createPasswordInput('add-password-input'));

		if (client_options.includes('api_token'))
			form.appendChild(createApiTokenInput('add-token-input'));

		if (client_type === 'SABnzbd') {
			fetchAPI('/settings', api_key)
			.then(settings => {
				appendSabnzbdSettings(form, {
					...settings.result,
					sabnzbd_enabled: true
				});
				showWindow('add-torrent-window');
			});
		} else {
			showWindow('add-torrent-window');
		};
	});
};

function saveAddTorrent() {
	usingApiKey()
	.then(api_key => {
		testAddTorrent(api_key).then(result => {
			if (!result)
				return;

			const form = document.querySelector('#add-torrent-form tbody');
			const data = {
				client_type: form.dataset.type,
				title: form.querySelector('#add-title-input').value,
				base_url: form.querySelector('#add-baseurl-input').value,
				username: form.querySelector('#add-username-input')?.value || null,
				password: form.querySelector('#add-password-input')?.value || null,
				api_token: form.querySelector('#add-token-input')?.value || null
			};
			sendAPI('POST', '/externalclients', api_key, {}, data)
			.then(response => {
				if (isSabnzbdForm(form))
					return sendAPI(
						'PUT',
						'/settings',
						api_key,
						{},
						getSabnzbdSettingsFromForm(form)
					);
			})
			.then(response => {
				loadTorrentClients(api_key);
				fillRemoteMappings(api_key);
				closeWindow();
			})
			.catch(e => {
				e.json().then(json => {
					if (
						json.error === "InvalidKeyValue"
						&& json.result.key === "password"
					) {
						const error = document.querySelector('#add-error');
						error.innerText = "*Username given but no password";
						hide([], [error]);
					};
				});
			});
		});
	});
};

async function testAddTorrent(api_key) {
	const error = document.querySelector('#add-error');
	hide([error]);
	const form = document.querySelector('#add-torrent-form tbody');
	const test_button = document.querySelector('#test-torrent-add');
	test_button.classList.remove('show-success', 'show-fail');
	const data = {
		client_type: form.dataset.type,
		base_url: form.querySelector('#add-baseurl-input').value,
		username: form.querySelector('#add-username-input')?.value || null,
		password: form.querySelector('#add-password-input')?.value || null,
		api_token: form.querySelector('#add-token-input')?.value || null,
	};
	return await sendAPI('POST', '/externalclients/test', api_key, {}, data)
	.then(response => response.json())
	.then(json => {
		if (json.result.success)
			// Test successful
			test_button.classList.add('show-success');
		else
			// Test failed
			test_button.classList.add('show-fail');
			error.innerText = json.result.description;
			hide([], [error]);
		return json.result.success;
	});
};

function loadTorrentClients(api_key) {
	fetchAPI('/externalclients', api_key)
	.then(json => {
		const usenet_table = document.querySelector('#usenet-client-list'),
			torrent_table = document.querySelector('#torrent-client-list'),
			add_mapping_select = document.querySelector('#add-mapping-client-input'),
			edit_mapping_select = document.querySelector('#edit-mapping-client-input');

		usenet_table.querySelectorAll('button').forEach(el => el.remove());
		torrent_table.querySelectorAll('button').forEach(el => el.remove());
		add_mapping_select.innerHTML = ''
		edit_mapping_select.innerHTML = ''

		json.result.forEach(client => {
			const entry = document.createElement('button');
			entry.onclick = (e) => loadEditTorrent(api_key, client.id);
			entry.innerText = client.title;

			if (isUsenetClient(client))
				usenet_table.appendChild(entry);
			else
				torrent_table.appendChild(entry);

			const option = document.createElement('option');
			option.innerText = client.title;
			option.value = client.id;
			add_mapping_select.appendChild(option);
			edit_mapping_select.appendChild(option.cloneNode(true));
		});

		document.querySelector('#usenet-client-list .empty-client-list').classList.toggle(
			'hidden',
			!!usenet_table.querySelector('button')
		);
		document.querySelector('#torrent-client-list .empty-client-list').classList.toggle(
			'hidden',
			!!torrent_table.querySelector('button')
		);
	});
};

function fillCredentials(api_key) {
	fetchAPI('/credentials', api_key)
	.then(json => {
		document.querySelectorAll('#mega-creds, #pixeldrain-creds').forEach(
			c => c.innerHTML = ''
		);
		json.result.forEach(result => {
			if (result.source === 'mega') {
				const row = document.querySelector('.pre-build-els .mega-cred-entry').cloneNode(true);
				row.querySelector('.mega-email').innerText = result.email;
				row.querySelector('.mega-password').innerText = result.password;
				row.querySelector('.delete-credential').onclick =
					e => sendAPI('DELETE', `/credentials/${result.id}`, api_key)
						.then(response => row.remove());
				document.querySelector('#mega-creds').appendChild(row);
			}
			else if (result.source === 'pixeldrain') {
				const row = document.querySelector('.pre-build-els .pixeldrain-cred-entry').cloneNode(true);
				row.querySelector('.pixeldrain-key').innerText = result.api_key;
				row.querySelector('.delete-credential').onclick =
					e => sendAPI('DELETE', `/credentials/${result.id}`, api_key)
						.then(response => row.remove());
				document.querySelector('#pixeldrain-creds').appendChild(row);
			};
		});
	});

	document.querySelectorAll('#mega-form input, #pixeldrain-form input').forEach(
		i => i.value = ''
	);
};

function addCredential() {
	hide([document.querySelector('#builtin-window p.error')]);

	const source = document.querySelector("#builtin-window").dataset.tag;
	let data;
	if (source === 'mega')
		data = {
			source: source,
			email: document.querySelector('#add-mega .mega-email input').value,
			password: document.querySelector('#add-mega .mega-password input').value
		};

	else if (source === 'pixeldrain')
		data = {
			source: source,
			api_key: document.querySelector('#add-pixeldrain .pixeldrain-key input').value
		};

	usingApiKey().then(api_key => {
		sendAPI('POST', '/credentials', api_key, {}, data)
		.then(response => fillCredentials(api_key))
		.catch(e => {
			if (e.status === 400)
				e.json().then(json => {
					if (json.error === "CredentialInvalid") {
						document.querySelector('#builtin-window p.error').innerText = "Invalid credentials";
					} else {
						document.querySelector('#builtin-window p.error').innerText = json.result.reason_text;
					}
					hide([], [document.querySelector('#builtin-window p.error')]);
				});
			else
				console.log(e);
		});
	});
};

const remoteMappings = {}
async function fillRemoteMappings(api_key) {
	const table = document.querySelector("#remote-mapping-list")
	table.innerHTML = ''

	const externalClients = await fetchAPI('/externalclients', api_key)
	const clientNames = Object.fromEntries(
		externalClients.result.map(c => [c.id, c.title])
	)

	const remoteMappingsResult = await fetchAPI('/remotemapping', api_key)
	remoteMappingsResult.result.forEach(m => {
		remoteMappings[m.id] = m

		const row = document.querySelector('.pre-build-els .remote-mapping-entry').cloneNode(true)
		row.dataset.id = m.id
		row.querySelector(".mapping-client").innerText = clientNames[m.external_download_client_id]
		row.querySelector(".mapping-remote").innerText = m.remote_path
		row.querySelector(".mapping-local").innerText = m.local_path
		row.querySelector(".edit-mapping").onclick = e => showEditRemoteMapping(m.id)
		row.querySelector(".delete-mapping").onclick = e => deleteRemoteMapping(m.id)

		table.appendChild(row)
	})
}

function showAddRemoteMapping() {
	hide([document.querySelector('#add-mapping-error')])
	document.querySelector('#add-mapping-remote-input').value = ''
	document.querySelector('#add-mapping-local-input').value = ''
	showWindow("add-mapping-window")
}

async function addRemoteMapping() {
	const data = {
		external_download_client_id: parseInt(document.querySelector('#add-mapping-client-input').value),
		remote_path: document.querySelector('#add-mapping-remote-input').value,
		local_path: document.querySelector('#add-mapping-local-input').value
	}

	const api_key = await usingApiKey()
	sendAPI("POST", "/remotemapping", api_key, {}, data)
	.then(response => {
		fillRemoteMappings(api_key)
		closeWindow()
	})
	.catch(async e => {
		const json = await e.json()
		if (json.error === "FolderNotFound") {
			document.querySelector('#add-mapping-error').innerText = "Local folder not found"
		} else if (json.error === "RemoteMappingInvalid") {
			document.querySelector('#add-mapping-error').innerText = "The local path or remote path is a child or parent of another local/remote path for the client"
		}
		hide([], [document.querySelector("#add-mapping-error")])
	})
}

function showEditRemoteMapping(id) {
	const data = remoteMappings[id]

	document.querySelector("#edit-mapping-window").dataset.id = id
	hide([document.querySelector('#edit-mapping-error')])
	document.querySelector('#edit-mapping-client-input').value = data.external_download_client_id
	document.querySelector('#edit-mapping-remote-input').value = data.remote_path
	document.querySelector('#edit-mapping-local-input').value = data.local_path
	showWindow("edit-mapping-window")
}

async function editRemoteMapping() {
	const id = parseInt(document.querySelector("#edit-mapping-window").dataset.id),
		data = {
			external_download_client_id: parseInt(document.querySelector('#edit-mapping-client-input').value),
			remote_path: document.querySelector('#edit-mapping-remote-input').value,
			local_path: document.querySelector('#edit-mapping-local-input').value
		},
		api_key = await usingApiKey()
	
	sendAPI("PUT", `/remotemapping/${id}`, api_key, {}, data)
	.then(response => {
		fillRemoteMappings(api_key)
		closeWindow()
	})
	.catch(async e => {
		const json = await e.json()
		if (json.error === "FolderNotFound") {
			document.querySelector('#edit-mapping-error').innerText = "Local folder not found"
		} else if (json.error === "RemoteMappingInvalid") {
			document.querySelector('#edit-mapping-error').innerText = "The local path or remote path is a child or parent of another local/remote path for the client"
		}
		hide([], [document.querySelector("#edit-mapping-error")])
	})
}

async function deleteRemoteMapping(id) {
	const api_key = await usingApiKey()
	sendAPI("DELETE", `/remotemapping/${id}`, api_key)
	document.querySelector(`#remote-mapping-list > tr[data-id="${id}"]`).remove()
}


// code run on load

usingApiKey()
.then(api_key => {
	fillCredentials(api_key);
	loadTorrentClients(api_key);
	fillRemoteMappings(api_key);
	document.querySelector('#delete-torrent-edit').onclick = e => deleteTorrent(api_key);
	document.querySelector('#test-torrent-edit').onclick = e => testEditTorrent(api_key);
	document.querySelector('#test-torrent-add').onclick = e => testAddTorrent(api_key);
	document.querySelector('#add-torrent-client').onclick = e => loadTorrentList(api_key);
});

document.querySelector('#edit-torrent-form').action = 'javascript:saveEditTorrent()';
document.querySelector('#add-torrent-form').action = 'javascript:saveAddTorrent()';
document.querySelectorAll('#cred-container > form').forEach(
	f => f.action = 'javascript:addCredential();'
);
document.querySelectorAll('#builtin-client-list > button').forEach(b => {
	const tag = b.dataset.tag;
	b.onclick = e => {
		document.querySelector('#builtin-window').dataset.tag = tag;
		hide([document.querySelector('#builtin-window p.error')]);
		document.querySelectorAll('#builtin-window input').forEach(i => i.value = '');

		showWindow('builtin-window');
	};
});
document.querySelector('#add-mapping-form').action = 'javascript:addRemoteMapping()'
document.querySelector('#add-remote-mapping').onclick = e => showAddRemoteMapping()
document.querySelector('#edit-mapping-form').action = 'javascript:editRemoteMapping()'
