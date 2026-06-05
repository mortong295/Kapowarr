const wantedState = {
	missing: {offset: 0, limit: 50, count: 0, total: 0},
	cutoff: {offset: 0, limit: 50, count: 0, total: 0}
};

function wantedProfileParams() {
	const profileFilter = document.querySelector('#wanted-profile-filter');
	return profileFilter.value ? {quality_profile_id: profileFilter.value} : {};
};

function wantedParams(kind) {
	return {
		...wantedProfileParams(),
		limit: wantedState[kind].limit,
		offset: wantedState[kind].offset
	};
};

function queueTask(button, api_key, body, queuedText) {
	button.disabled = true;
	button.innerText = queuedText;
	sendAPI('POST', '/system/tasks', api_key, {}, body)
		.then(() => {
			button.disabled = false;
			button.innerText = button.dataset.label;
		});
};

function queueIssueSearch(api_key, item, button=null) {
	const payload = {
		cmd: 'auto_search_issue',
		volume_id: item.volume_id,
		issue_id: item.issue_id
	};
	if (button) {
		button.dataset.label = button.innerText;
		queueTask(button, api_key, payload, 'Queued');
		return;
	};
	return sendAPI('POST', '/system/tasks', api_key, {}, payload);
};

function addIssueControls(row, item, api_key) {
	const checkbox = row.querySelector('input[type="checkbox"]');
	checkbox.dataset.volumeId = item.volume_id;
	checkbox.dataset.issueId = item.issue_id;
	const button = row.querySelector('button');
	button.onclick = () => queueIssueSearch(api_key, item, button);
};

function addWantedRow(item, api_key) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td><input class="wanted-select" type="checkbox"></td>
		<td><a></a></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td><button type="button">Search</button></td>
	`;
	const link = row.querySelector('a');
	link.href = `${url_base}/volumes/${item.volume_id}`;
	link.innerText = `${item.volume_title} (${item.year || 'Unknown'})`;
	row.children[2].innerText = `#${item.issue_number}${item.issue_title ? ` - ${item.issue_title}` : ''}`;
	row.children[3].innerText = item.date || 'Unknown';
	row.children[4].innerText = item.publisher || 'Unknown';
	row.children[5].innerText = item.quality_profile_name || 'Unknown';
	row.children[6].innerText = item.decision || 'Missing monitored issue';
	addIssueControls(row, item, api_key);
	document.querySelector('#wanted-items').appendChild(row);
};

function addWantedCutoffRow(item, api_key) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td><input class="wanted-select" type="checkbox"></td>
		<td><a></a></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td><button type="button">Search</button></td>
	`;
	const link = row.querySelector('a');
	link.href = `${url_base}/volumes/${item.volume_id}`;
	link.innerText = `${item.volume_title} (${item.year || 'Unknown'})`;
	row.children[2].innerText = `#${item.issue_number}${item.issue_title ? ` - ${item.issue_title}` : ''}`;
	row.children[3].innerText = `${(item.quality_format || 'unknown').toUpperCase()} (${item.quality_score || 0})`;
	row.children[4].innerText = `${(item.cutoff || 'unknown').toUpperCase()} (${item.cutoff_score || 0})`;
	row.children[5].innerText = item.quality_profile_name || 'Unknown';
	row.children[6].innerText = item.decision || item.quality_profile_issue || 'Below cutoff';
	addIssueControls(row, item, api_key);
	document.querySelector('#wanted-cutoff-items').appendChild(row);
};

function addWantedArcRow(item, api_key) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
	`;
	row.children[0].innerText = item.story_arc_title;
	row.children[1].innerText = item.reading_order;
	row.children[2].innerText = item.issue_number ? `#${item.issue_number}` : (item.issue_title || 'Unmatched issue');
	row.children[3].innerText = item.volume_title || 'Unmatched volume';
	if (item.volume_id && item.issue_id) {
		const button = document.createElement('button');
		button.type = 'button';
		button.innerText = 'Search';
		button.onclick = () => queueIssueSearch(api_key, item, button);
		row.children[4].appendChild(button);
	} else {
		row.children[4].innerText = 'Match first';
	};
	document.querySelector('#wanted-arc-items').appendChild(row);
};

function updatePager(kind, prefix) {
	const state = wantedState[kind];
	const page = Math.floor(state.offset / state.limit) + 1;
	const pages = Math.max(1, Math.ceil(state.total / state.limit));
	const start = state.total ? state.offset + 1 : 0;
	const end = Math.min(state.offset + state.count, state.total);
	document.querySelector(`#${prefix}-page-label`).innerText =
		`Page ${page} of ${pages} (${start}-${end} of ${state.total})`;
	document.querySelector(`#${prefix}-prev-button`).disabled = state.offset === 0;
	document.querySelector(`#${prefix}-next-button`).disabled =
		state.offset + state.limit >= state.total;
};

function loadMissing(api_key) {
	const wantedItems = document.querySelector('#wanted-items');
	wantedItems.innerHTML = '';
	document.querySelector('#wanted-empty').classList.add('hidden');
	fetchAPI('/wanted/missing', api_key, wantedParams('missing'))
		.then(json => {
			const items = json.result.items;
			wantedState.missing.count = items.length;
			wantedState.missing.total = json.result.total || 0;
			document.querySelector('#wanted-summary').innerText =
				`${wantedState.missing.total} missing monitored issue(s)`;
			if (!items.length)
				document.querySelector('#wanted-empty').classList.remove('hidden');
			else
				items.forEach(item => addWantedRow(item, api_key));
			updatePager('missing', 'wanted');
		});
};

function loadCutoffUnmet(api_key) {
	const cutoffItems = document.querySelector('#wanted-cutoff-items');
	cutoffItems.innerHTML = '';
	document.querySelector('#wanted-cutoff-empty').classList.add('hidden');
	fetchAPI('/wanted/cutoff-unmet', api_key, wantedParams('cutoff'))
		.then(json => {
			const items = json.result.items;
			wantedState.cutoff.count = items.length;
			wantedState.cutoff.total = json.result.total || 0;
			document.querySelector('#wanted-cutoff-summary').innerText =
				`${wantedState.cutoff.total} cutoff-unmet issue(s)`;
			if (!items.length)
				document.querySelector('#wanted-cutoff-empty').classList.remove('hidden');
			else
				items.forEach(item => addWantedCutoffRow(item, api_key));
			updatePager('cutoff', 'wanted-cutoff');
		});
};

function loadStoryArcs(api_key) {
	const arcItems = document.querySelector('#wanted-arc-items');
	arcItems.innerHTML = '';
	document.querySelector('#wanted-arc-empty').classList.add('hidden');
	fetchAPI('/storyarcs/missing', api_key)
		.then(json => {
			const items = json.result;
			document.querySelector('#wanted-arc-summary').innerText = `${items.length} missing story arc issue(s)`;
			if (!items.length)
				document.querySelector('#wanted-arc-empty').classList.remove('hidden');
			else
				items.forEach(item => addWantedArcRow(item, api_key));
		});
};

function selectedWantedItems() {
	return Array.from(document.querySelectorAll('.wanted-select:checked'))
		.map(input => ({
			volume_id: parseInt(input.dataset.volumeId),
			issue_id: parseInt(input.dataset.issueId)
		}))
		.filter(item => item.volume_id && item.issue_id);
};

usingApiKey().then(api_key => {
	const wantedButton = document.querySelector('#search-wanted-button');
	wantedButton.dataset.label = wantedButton.innerText;
	wantedButton.onclick = () => queueTask(
		wantedButton,
		api_key,
		{cmd: 'search_wanted_missing'},
		'Search queued...'
	);
	const cutoffButton = document.querySelector('#search-cutoff-button');
	cutoffButton.dataset.label = cutoffButton.innerText;
	cutoffButton.onclick = () => queueTask(
		cutoffButton,
		api_key,
		{cmd: 'search_wanted_cutoff_unmet'},
		'Cutoff search queued...'
	);
	const arcButton = document.querySelector('#search-story-arcs-button');
	arcButton.dataset.label = arcButton.innerText;
	arcButton.onclick = () => queueTask(
		arcButton,
		api_key,
		{cmd: 'search_story_arc_missing'},
		'Story arc search queued...'
	);
	const selectedButton = document.querySelector('#search-selected-button');
	selectedButton.dataset.label = selectedButton.innerText;
	selectedButton.onclick = () => {
		selectedButton.disabled = true;
		selectedButton.innerText = 'Queueing...';
		Promise.all(selectedWantedItems().map(item => queueIssueSearch(api_key, item)))
			.then(() => {
				selectedButton.disabled = false;
				selectedButton.innerText = selectedButton.dataset.label;
			});
	};

	document.querySelector('#wanted-select-all').onchange = event => {
		document.querySelectorAll('#wanted-items .wanted-select')
			.forEach(input => input.checked = event.target.checked);
	};
	document.querySelector('#wanted-cutoff-select-all').onchange = event => {
		document.querySelectorAll('#wanted-cutoff-items .wanted-select')
			.forEach(input => input.checked = event.target.checked);
	};
	document.querySelector('#wanted-prev-button').onclick = () => {
		wantedState.missing.offset = Math.max(0, wantedState.missing.offset - wantedState.missing.limit);
		loadMissing(api_key);
	};
	document.querySelector('#wanted-next-button').onclick = () => {
		wantedState.missing.offset += wantedState.missing.limit;
		loadMissing(api_key);
	};
	document.querySelector('#wanted-cutoff-prev-button').onclick = () => {
		wantedState.cutoff.offset = Math.max(0, wantedState.cutoff.offset - wantedState.cutoff.limit);
		loadCutoffUnmet(api_key);
	};
	document.querySelector('#wanted-cutoff-next-button').onclick = () => {
		wantedState.cutoff.offset += wantedState.cutoff.limit;
		loadCutoffUnmet(api_key);
	};

	fetchAPI('/profiles', api_key)
		.then(json => {
			const profileFilter = document.querySelector('#wanted-profile-filter');
			json.result.forEach(profile => {
				const option = document.createElement('option');
				option.value = profile.id;
				option.innerText = profile.name;
				profileFilter.appendChild(option);
			});
			profileFilter.onchange = () => {
				wantedState.missing.offset = 0;
				wantedState.cutoff.offset = 0;
				loadMissing(api_key);
				loadCutoffUnmet(api_key);
			};
			loadMissing(api_key);
			loadCutoffUnmet(api_key);
		});

	loadStoryArcs(api_key);
});
