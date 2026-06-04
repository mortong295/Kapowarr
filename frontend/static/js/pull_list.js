function addPullListRow(item, api_key) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td></td>
		<td><button type="button">Delete</button></td>
	`;
	row.children[0].innerText = item.release_date || 'Unknown';
	row.children[1].innerText = item.publisher || 'Unknown';
	row.children[2].innerText = item.series;
	row.children[3].innerText = `#${item.issue_number || '?'}${item.title ? ` - ${item.title}` : ''}`;
	row.children[4].innerText = item.volume_id ? `Matched (${item.match_confidence}%)` : 'Unmatched';
	row.children[5].innerText = item.status || 'pending';
	row.querySelector('button').onclick = event => {
		event.target.disabled = true;
		sendAPI('DELETE', `/pulllist/${item.id}`, api_key)
			.then(() => loadPullList(api_key));
	};
	document.querySelector('#pull-list-items').appendChild(row);
};

function loadPullList(api_key) {
	const body = document.querySelector('#pull-list-items');
	body.innerHTML = '';
	document.querySelector('#pull-list-empty').classList.add('hidden');
	fetchAPI('/pulllist', api_key)
		.then(json => {
			const items = json.result;
			document.querySelector('#pull-list-summary').innerText = `${items.length} pull-list item(s)`;
			if (!items.length) {
				document.querySelector('#pull-list-empty').classList.remove('hidden');
				return;
			};
			items.forEach(item => addPullListRow(item, api_key));
		});
};

function clearPullListForm() {
	document.querySelector('#pull-release-date-input').value = '';
	document.querySelector('#pull-publisher-input').value = '';
	document.querySelector('#pull-series-input').value = '';
	document.querySelector('#pull-issue-input').value = '';
	document.querySelector('#pull-title-input').value = '';
};

function addManualPullListItem(api_key) {
	const feedback = document.querySelector('#pull-list-form-feedback');
	const payload = {
		provider: 'manual',
		release_date: document.querySelector('#pull-release-date-input').value,
		publisher: document.querySelector('#pull-publisher-input').value,
		series: document.querySelector('#pull-series-input').value,
		issue_number: document.querySelector('#pull-issue-input').value,
		title: document.querySelector('#pull-title-input').value,
		status: 'pending'
	};
	feedback.innerText = 'Adding pull-list item…';
	sendAPI('POST', '/pulllist', api_key, {}, payload)
		.then(response => response.json())
		.then(json => {
			if (json.error) {
				feedback.innerText = 'Failed to add pull-list item.';
				return;
			};
			feedback.innerText = json.result.volume_id
				? `Added and matched at ${json.result.match_confidence}% confidence.`
				: 'Added but not matched to a monitored volume yet.';
			clearPullListForm();
			loadPullList(api_key);
		});
};

usingApiKey().then(api_key => {
	document.querySelector('#pull-list-form').onsubmit = event => {
		event.preventDefault();
		addManualPullListItem(api_key);
	};
	document.querySelector('#sync-import-lists-button').onclick = event => {
		event.target.disabled = true;
		event.target.innerText = 'Sync queued…';
		sendAPI('POST', '/system/tasks', api_key, {}, {cmd: 'sync_import_lists'})
			.then(() => {
				event.target.innerText = 'Sync Import Lists';
				event.target.disabled = false;
				setTimeout(() => loadPullList(api_key), 1500);
			});
	};
	document.querySelector('#search-pull-list-button').onclick = event => {
		event.target.disabled = true;
		event.target.innerText = 'Search queued…';
		sendAPI('POST', '/system/tasks', api_key, {}, {cmd: 'search_pull_list'})
			.then(() => {
				event.target.innerText = 'Search Pull List';
				event.target.disabled = false;
				setTimeout(() => loadPullList(api_key), 1500);
			});
	};
	loadPullList(api_key);
});
