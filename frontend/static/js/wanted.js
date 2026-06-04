function addWantedRow(item) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td><a></a></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
	`;
	const link = row.querySelector('a');
	link.href = `${url_base}/volumes/${item.volume_id}`;
	link.innerText = `${item.volume_title} (${item.year || 'Unknown'})`;
	row.children[1].innerText = `#${item.issue_number}${item.issue_title ? ` - ${item.issue_title}` : ''}`;
	row.children[2].innerText = item.date || 'Unknown';
	row.children[3].innerText = item.publisher || 'Unknown';
	row.children[4].innerText = item.quality_profile_name || 'Unknown';
	document.querySelector('#wanted-items').appendChild(row);
};

function addWantedCutoffRow(item) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td><a></a></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
	`;
	const link = row.querySelector('a');
	link.href = `${url_base}/volumes/${item.volume_id}`;
	link.innerText = `${item.volume_title} (${item.year || 'Unknown'})`;
	row.children[1].innerText = `#${item.issue_number}${item.issue_title ? ` - ${item.issue_title}` : ''}`;
	row.children[2].innerText = `${(item.quality_format || 'unknown').toUpperCase()} (${item.quality_score || 0})`;
	row.children[3].innerText = `${(item.cutoff || 'unknown').toUpperCase()} (${item.cutoff_score || 0})`;
	row.children[4].innerText = item.quality_profile_name || 'Unknown';
	document.querySelector('#wanted-cutoff-items').appendChild(row);
};

function addWantedArcRow(item) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td></td>
		<td></td>
		<td></td>
		<td></td>
	`;
	row.children[0].innerText = item.story_arc_title;
	row.children[1].innerText = item.reading_order;
	row.children[2].innerText = item.issue_number ? `#${item.issue_number}` : (item.issue_title || 'Unmatched issue');
	row.children[3].innerText = item.volume_title || 'Unmatched volume';
	document.querySelector('#wanted-arc-items').appendChild(row);
};

function wantedProfileQuery() {
	const profileFilter = document.querySelector('#wanted-profile-filter');
	return profileFilter.value ? `?quality_profile_id=${profileFilter.value}` : '';
};

function loadMissing(api_key) {
	const wantedItems = document.querySelector('#wanted-items');
	wantedItems.innerHTML = '';
	document.querySelector('#wanted-empty').classList.add('hidden');
	fetchAPI(`/wanted/missing${wantedProfileQuery()}`, api_key)
		.then(json => {
			const items = json.result.items;
			document.querySelector('#wanted-summary').innerText = `${items.length} missing monitored issue(s)`;
			if (!items.length)
				document.querySelector('#wanted-empty').classList.remove('hidden');
			else
				items.forEach(addWantedRow);
		});
};

function loadCutoffUnmet(api_key) {
	const cutoffItems = document.querySelector('#wanted-cutoff-items');
	cutoffItems.innerHTML = '';
	document.querySelector('#wanted-cutoff-empty').classList.add('hidden');
	fetchAPI(`/wanted/cutoff-unmet${wantedProfileQuery()}`, api_key)
		.then(json => {
			const items = json.result.items;
			document.querySelector('#wanted-cutoff-summary').innerText = `${items.length} cutoff-unmet issue(s)`;
			if (!items.length)
				document.querySelector('#wanted-cutoff-empty').classList.remove('hidden');
			else
				items.forEach(addWantedCutoffRow);
		});
};

function queueTask(button, api_key, cmd, queuedText) {
	button.disabled = true;
	button.innerText = queuedText;
	sendAPI('POST', '/system/tasks', api_key, {}, {cmd: cmd})
		.then(() => {
			button.disabled = false;
			button.innerText = button.dataset.label;
		});
};

usingApiKey().then(api_key => {
	const wantedButton = document.querySelector('#search-wanted-button');
	wantedButton.dataset.label = wantedButton.innerText;
	wantedButton.onclick = () => queueTask(
		wantedButton,
		api_key,
		'search_wanted_missing',
		'Search queued…'
	);
	const cutoffButton = document.querySelector('#search-cutoff-button');
	cutoffButton.dataset.label = cutoffButton.innerText;
	cutoffButton.onclick = () => queueTask(
		cutoffButton,
		api_key,
		'search_wanted_cutoff_unmet',
		'Cutoff search queued…'
	);
	const arcButton = document.querySelector('#search-story-arcs-button');
	arcButton.dataset.label = arcButton.innerText;
	arcButton.onclick = () => queueTask(
		arcButton,
		api_key,
		'search_story_arc_missing',
		'Story arc search queued…'
	);

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
				loadMissing(api_key);
				loadCutoffUnmet(api_key);
			};
			loadMissing(api_key);
			loadCutoffUnmet(api_key);
		});

	fetchAPI('/storyarcs/missing', api_key)
		.then(json => {
			const items = json.result;
			document.querySelector('#wanted-arc-summary').innerText = `${items.length} missing story arc issue(s)`;
			if (!items.length)
				document.querySelector('#wanted-arc-empty').classList.remove('hidden');
			else
				items.forEach(addWantedArcRow);
		});
});
