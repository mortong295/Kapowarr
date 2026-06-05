const feature = document.querySelector('main').dataset.feature;
const providerFeatures = ['indexers', 'connections', 'importlists'];
const providerImplementations = {
	indexers: ['getcomics', 'newznab', 'torznab', 'prowlarr', 'rawrss'],
	connections: ['webhook', 'discord', 'gotify', 'emby', 'plex', 'jellyfin'],
	importlists: ['json', 'csv', 'pulllist', 'mylar', 'comicvine']
};
const providerDefaults = {
	indexers: {
		getcomics: {
			description: 'Built-in GetComics source. No extra settings are required.',
			settings: {source: 'GetComics'}
		},
		newznab: {
			description: 'Newznab-compatible usenet indexer. Use the base site URL; Kapowarr appends /api.',
			settings: {base_url: '', api_key: '', categories: '7030'}
		},
		torznab: {
			description: 'Torznab-compatible torrent indexer. Use Prowlarr or Jackett category IDs where needed.',
			settings: {base_url: '', api_key: '', categories: '7030'}
		},
		prowlarr: {
			description: 'Prowlarr indexer proxy. Kapowarr asks Prowlarr to search configured comic-capable indexers.',
			settings: {base_url: '', api_key: '', categories: '7030'}
		},
		rawrss: {
			description: 'Plain RSS or Atom feed searched by title terms.',
			settings: {feed_url: ''}
		}
	},
	connections: {
		webhook: {
			description: 'POST the full Kapowarr event payload to another automation endpoint.',
			settings: {url: '', headers: {}}
		},
		discord: {
			description: 'Send grab/import/failure events to a Discord webhook.',
			settings: {webhook_url: ''}
		},
		gotify: {
			description: 'Send notifications to Gotify.',
			settings: {base_url: '', token: '', priority: 5}
		},
		emby: {
			description: 'Refresh Emby after Kapowarr events. Omit item_id for a full library refresh.',
			settings: {base_url: '', api_key: '', item_id: ''}
		},
		plex: {
			description: 'Refresh a Plex library section after Kapowarr events. Omit section_id to refresh all sections.',
			settings: {base_url: '', token: '', section_id: 'all'}
		},
		jellyfin: {
			description: 'Refresh Jellyfin after Kapowarr events. Omit item_id for a full library refresh.',
			settings: {base_url: '', api_key: '', item_id: ''}
		}
	},
	importlists: {
		json: {
			description: 'JSON list with an items or pull_list array.',
			settings: {url: '', items: []}
		},
		csv: {
			description: 'CSV with release_date,publisher,series,issue_number,title columns.',
			settings: {url: '', body: ''}
		},
		pulllist: {
			description: 'Weekly pull-list feed in RSS, JSON, or CSV format.',
			settings: {url: '', format: 'rss'}
		},
		mylar: {
			description: 'Mylar-compatible exported watch/pull list JSON.',
			settings: {url: '', items: []}
		},
		comicvine: {
			description: 'Live ComicVine import source for story arcs and volume issue lists.',
			settings: {story_arc_ids: '', volume_ids: ''}
		}
	}
};
const providerSchemas = {
	indexers: {
		getcomics: [],
		newznab: [
			{key: 'base_url', label: 'Base URL', type: 'url'},
			{key: 'api_key', label: 'API Key', type: 'password'},
			{key: 'categories', label: 'Categories', type: 'text'}
		],
		torznab: [
			{key: 'base_url', label: 'Base URL', type: 'url'},
			{key: 'api_key', label: 'API Key', type: 'password'},
			{key: 'categories', label: 'Categories', type: 'text'}
		],
		prowlarr: [
			{key: 'base_url', label: 'Base URL', type: 'url'},
			{key: 'api_key', label: 'API Key', type: 'password'},
			{key: 'categories', label: 'Categories', type: 'text'}
		],
		rawrss: [
			{key: 'feed_url', label: 'Feed URL', type: 'url'}
		]
	},
	connections: {
		webhook: [
			{key: 'url', label: 'Webhook URL', type: 'url'},
			{key: 'headers', label: 'Headers JSON', type: 'json'}
		],
		discord: [
			{key: 'webhook_url', label: 'Webhook URL', type: 'url'}
		],
		gotify: [
			{key: 'base_url', label: 'Base URL', type: 'url'},
			{key: 'token', label: 'Token', type: 'password'},
			{key: 'priority', label: 'Priority', type: 'number'}
		],
		emby: [
			{key: 'base_url', label: 'Base URL', type: 'url'},
			{key: 'api_key', label: 'API Key', type: 'password'},
			{key: 'item_id', label: 'Item ID', type: 'text'},
			{key: 'path', label: 'Library Path', type: 'text'}
		],
		plex: [
			{key: 'base_url', label: 'Base URL', type: 'url'},
			{key: 'token', label: 'Token', type: 'password'},
			{key: 'section_id', label: 'Section ID', type: 'text'},
			{key: 'path', label: 'Library Path', type: 'text'}
		],
		jellyfin: [
			{key: 'base_url', label: 'Base URL', type: 'url'},
			{key: 'api_key', label: 'API Key', type: 'password'},
			{key: 'item_id', label: 'Item ID', type: 'text'},
			{key: 'path', label: 'Library Path', type: 'text'}
		]
	},
	importlists: {
		json: [
			{key: 'url', label: 'URL', type: 'url'},
			{key: 'body', label: 'Inline JSON', type: 'textarea'}
		],
		csv: [
			{key: 'url', label: 'URL', type: 'url'},
			{key: 'body', label: 'Inline CSV', type: 'textarea'}
		],
		pulllist: [
			{key: 'url', label: 'Feed URL', type: 'url'},
			{key: 'format', label: 'Format', type: 'select', options: ['rss', 'json', 'csv']}
		],
		mylar: [
			{key: 'url', label: 'Export URL', type: 'url'},
			{key: 'body', label: 'Inline Export JSON', type: 'textarea'}
		],
		comicvine: [
			{key: 'api_key', label: 'API Key Override', type: 'password'},
			{key: 'story_arc_ids', label: 'Story Arc IDs', type: 'text'},
			{key: 'volume_ids', label: 'Volume IDs', type: 'text'}
		]
	}
};
let apiKey = null;
let currentItems = [];
let editingItem = null;

function parseList(value) {
	return value.split(',')
		.map(item => item.trim())
		.filter(item => item);
};

function parseJSONField(selector, fallback) {
	const raw = document.querySelector(selector).value.trim();
	if (!raw) return fallback;
	return JSON.parse(raw);
};

function parseJSONFieldFallback(selector, fallback) {
	try {
		return parseJSONField(selector, fallback);
	} catch {
		return fallback;
	};
};

function showFeedback(message, error=false) {
	const feedback = document.querySelector('#settings-feedback');
	feedback.innerText = message;
	feedback.classList.toggle('error', error);
	feedback.classList.remove('hidden');
};

function resetForm() {
	editingItem = null;
	document.querySelector('#settings-editor-title').innerText = `Add ${featureLabel()}`;
	document.querySelector('#settings-editor-form').reset();
	document.querySelector('#provider-settings-input').value = '{}';
	document.querySelector('#provider-tags-input').value = '';
	document.querySelector('#provider-events-input').value = '';
	document.querySelector('#profile-custom-formats-input').value = '{}';
	document.querySelector('#profile-metadata-input').value = JSON.stringify({
		write_comicinfo: true,
		write_series_json: true,
		embed_comicinfo: false,
		preserve_existing: true
	}, null, 2);
	document.querySelector('#provider-enabled-input').checked = true;
	document.querySelector('#profile-upgrade-input').checked = true;
	document.querySelector('#provider-priority-input').value = 25;
	document.querySelector('#profile-cutoff-input').value = 'cbz';
	document.querySelector('#profile-allowed-input').value = 'cbz,cbr,pdf,epub';
	document.querySelector('#profile-preferred-input').value = 'cbz,cbr';
	updateImplementationHelp();
};

function featureLabel() {
	return feature === 'profiles' ? 'Profile' : 'Provider';
};

function endpointForItem(item=null) {
	if (item && item.id) return `/${feature}/${item.id}`;
	return `/${feature}`;
};

function providerPayload() {
	return {
		name: document.querySelector('#provider-name-input').value,
		implementation: document.querySelector('#provider-implementation-input').value,
		enabled: document.querySelector('#provider-enabled-input').checked,
		priority: parseInt(document.querySelector('#provider-priority-input').value),
		settings: providerSettingsPayload(),
		tags: parseList(document.querySelector('#provider-tags-input').value),
		events: parseList(document.querySelector('#provider-events-input').value)
	};
};

function implementationDefault() {
	const implementation = document.querySelector('#provider-implementation-input').value;
	return (providerDefaults[feature] || {})[implementation] || null;
};

function implementationSchema() {
	const implementation = document.querySelector('#provider-implementation-input').value;
	return ((providerSchemas[feature] || {})[implementation] || []);
};

function providerSettingsPayload() {
	const settings = parseJSONFieldFallback('#provider-settings-input', {});
	implementationSchema().forEach(field => {
		const input = document.querySelector(`[data-provider-setting="${field.key}"]`);
		if (!input) return;
		if (field.type === 'checkbox') settings[field.key] = input.checked;
		else if (field.type === 'number') settings[field.key] = parseInt(input.value || 0);
		else if (field.type === 'json') {
			try {
				settings[field.key] = JSON.parse(input.value || '{}');
			} catch {
				settings[field.key] = {};
			};
		}
		else settings[field.key] = input.value;
	});
	return settings;
};

function syncSchemaToJSON() {
	const settings = providerSettingsPayload();
	document.querySelector('#provider-settings-input').value = JSON.stringify(settings, null, 2);
};

function renderSchemaFields(settings=null) {
	const container = document.querySelector('#provider-schema-fields');
	if (!container) return;
	container.innerHTML = '';
	const schema = implementationSchema();
	container.classList.toggle('hidden', !schema.length);
	const values = settings || parseJSONFieldFallback('#provider-settings-input', {});
	schema.forEach(field => {
		const label = document.createElement('label');
		label.innerHTML = `<span>${field.label}</span>`;
		let input;
		if (field.type === 'textarea' || field.type === 'json') {
			input = document.createElement('textarea');
		} else if (field.type === 'select') {
			input = document.createElement('select');
			(field.options || []).forEach(optionValue => {
				const option = document.createElement('option');
				option.value = optionValue;
				option.innerText = optionValue.toUpperCase();
				input.appendChild(option);
			});
		} else {
			input = document.createElement('input');
			input.type = field.type || 'text';
		};
		input.dataset.providerSetting = field.key;
		const value = values[field.key];
		if (field.type === 'checkbox') input.checked = value !== false;
		else if (field.type === 'json') input.value = JSON.stringify(value || {}, null, 2);
		else input.value = value === undefined || value === null ? '' : value;
		input.oninput = syncSchemaToJSON;
		input.onchange = syncSchemaToJSON;
		label.appendChild(input);
		container.appendChild(label);
	});
};

function updateImplementationHelp(fill=false) {
	const help = document.querySelector('#provider-settings-help');
	if (!help) return;
	const preset = implementationDefault();
	if (!preset) {
		help.innerHTML = '';
		return;
	};
	help.innerHTML = `
		<strong>${preset.description}</strong>
		<code></code>
	`;
	help.querySelector('code').innerText = JSON.stringify(preset.settings, null, 2);
	if (fill && !editingItem)
		document.querySelector('#provider-settings-input').value = JSON.stringify(
			preset.settings,
			null,
			2
		);
	renderSchemaFields();
};

function profilePayload() {
	return {
		name: document.querySelector('#profile-name-input').value,
		upgrade_allowed: document.querySelector('#profile-upgrade-input').checked,
		cutoff: document.querySelector('#profile-cutoff-input').value,
		allowed_formats: parseList(document.querySelector('#profile-allowed-input').value),
		preferred_formats: parseList(document.querySelector('#profile-preferred-input').value),
		custom_formats: parseJSONField('#profile-custom-formats-input', {}),
		metadata_profile: parseJSONField('#profile-metadata-input', {})
	};
};

function fillProviderForm(item) {
	document.querySelector('#provider-name-input').value = item.name || '';
	document.querySelector('#provider-implementation-input').value = item.implementation || '';
	document.querySelector('#provider-enabled-input').checked = item.enabled !== false;
	document.querySelector('#provider-priority-input').value = item.priority || 25;
	document.querySelector('#provider-settings-input').value = JSON.stringify(item.settings || {}, null, 2);
	document.querySelector('#provider-tags-input').value = (item.tags || []).join(',');
	document.querySelector('#provider-events-input').value = (item.events || []).join(',');
	updateImplementationHelp();
	renderSchemaFields(item.settings || {});
};

function fillProfileForm(item) {
	document.querySelector('#profile-name-input').value = item.name || '';
	document.querySelector('#profile-upgrade-input').checked = item.upgrade_allowed !== false;
	document.querySelector('#profile-cutoff-input').value = item.cutoff || '';
	document.querySelector('#profile-allowed-input').value = (item.allowed_formats || []).join(',');
	document.querySelector('#profile-preferred-input').value = (item.preferred_formats || []).join(',');
	document.querySelector('#profile-custom-formats-input').value = JSON.stringify(item.custom_formats || {}, null, 2);
	document.querySelector('#profile-metadata-input').value = JSON.stringify(item.metadata_profile || {}, null, 2);
};

function editItem(item) {
	editingItem = item;
	document.querySelector('#settings-editor-title').innerText = `Edit ${item.name}`;
	if (feature === 'profiles') fillProfileForm(item);
	else fillProviderForm(item);
	document.querySelector('#settings-editor').scrollIntoView({behavior: 'smooth'});
};

function deleteItem(item) {
	if (!confirm(`Delete ${item.name}?`)) return;
	sendAPI('DELETE', endpointForItem(item), apiKey)
		.then(() => loadItems())
		.then(() => showFeedback(`${item.name} deleted.`));
};

function testItem(item=null) {
	const payload = item || (feature === 'profiles' ? profilePayload() : providerPayload());
	if (feature === 'profiles') {
		showFeedback('Profiles do not have a connection test.');
		return;
	};
	sendAPI('POST', `/${feature}/test`, apiKey, {}, payload)
		.then(response => response.json())
		.then(json => showFeedback(json.result.message || json.result.status));
};

function syncImportList(item) {
	sendAPI('POST', `/importlists/${item.id}/sync`, apiKey, {})
		.then(response => response.json())
		.then(json => showFeedback(json.result.message || 'Import list synced.'));
};

function addActionButton(container, label, onclick) {
	const button = document.createElement('button');
	button.type = 'button';
	button.innerText = label;
	button.onclick = onclick;
	container.appendChild(button);
};

function addFeatureCard(item) {
	const card = document.createElement('article');
	card.className = 'arr-card';
	card.innerHTML = `
		<h2></h2>
		<p class="arr-status"></p>
		<p></p>
		<dl class="arr-provider-meta hidden">
			<dt>Implementation</dt><dd class="provider-implementation"></dd>
			<dt>Priority</dt><dd class="provider-priority"></dd>
		</dl>
		<div class="arr-card-actions"></div>
	`;
	card.querySelector('h2').innerText = item.name;
	card.querySelector('.arr-status').innerText = item.status || (
		item.upgrade_allowed === false ? 'No upgrades' : 'Available'
	);
	card.querySelector('p').innerText = item.description || (
		item.enabled === false
			? 'Provider is disabled and will not be used.'
			: summaryForItem(item)
	);
	if (item.implementation) {
		card.querySelector('.arr-provider-meta').classList.remove('hidden');
		card.querySelector('.provider-implementation').innerText = item.implementation;
		card.querySelector('.provider-priority').innerText = item.priority;
	}
	const actions = card.querySelector('.arr-card-actions');
	addActionButton(actions, 'Edit', () => editItem(item));
	if (feature !== 'profiles') addActionButton(actions, 'Test', () => testItem(item));
	if (feature === 'importlists') addActionButton(actions, 'Sync', () => syncImportList(item));
	addActionButton(actions, 'Delete', () => deleteItem(item));
	document.querySelector('#feature-cards').appendChild(card);
};

function summaryForItem(item) {
	if (feature === 'profiles') {
		return `Allowed: ${(item.allowed_formats || []).join(', ') || 'none'}; preferred: ${(item.preferred_formats || []).join(', ') || 'none'}.`;
	};
	return 'Provider is enabled and available to Kapowarr.';
};

function loadItems() {
	return fetchAPI(`/${feature}`, apiKey)
		.then(json => {
			currentItems = json.result;
			const cards = document.querySelector('#feature-cards');
			cards.innerHTML = '';
			currentItems.forEach(addFeatureCard);
		});
};

function saveItem(event) {
	event.preventDefault();
	let payload;
	try {
		payload = feature === 'profiles' ? profilePayload() : providerPayload();
	} catch (error) {
		showFeedback(`Invalid JSON: ${error.message}`, true);
		return;
	}
	const method = editingItem ? 'PUT' : 'POST';
	sendAPI(method, endpointForItem(editingItem), apiKey, {}, payload)
		.then(response => response.json())
		.then(json => {
			resetForm();
			return loadItems().then(() => showFeedback(`${json.result.name} saved.`));
		})
		.catch(() => showFeedback('Unable to save settings entry.', true));
};

function buildImplementationOptions() {
	const select = document.querySelector('#provider-implementation-input');
	select.innerHTML = '';
	(providerImplementations[feature] || []).forEach(implementation => {
		const option = document.createElement('option');
		option.value = implementation;
		option.innerText = implementation;
		select.appendChild(option);
	});
	select.onchange = () => {
		updateImplementationHelp(true);
		renderSchemaFields();
	};
};

function setupFeatureForm() {
	document.querySelector('#settings-editor-form').onsubmit = saveItem;
	document.querySelector('#settings-cancel-button').onclick = resetForm;
	document.querySelector('#settings-test-button').onclick = () => testItem();
	document.querySelector('#settings-test-button').classList.toggle('hidden', feature === 'profiles');
	document.querySelector('#profile-fields').classList.toggle('hidden', feature !== 'profiles');
	document.querySelector('#provider-fields').classList.toggle('hidden', !providerFeatures.includes(feature));
	buildImplementationOptions();
	resetForm();
};

usingApiKey().then(key => {
	apiKey = key;
	setupFeatureForm();
	loadItems();
});
