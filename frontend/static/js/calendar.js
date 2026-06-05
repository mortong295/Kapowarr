function addCalendarRow(item) {
	const row = document.createElement('tr');
	const status = item.downloaded ? 'Downloaded' : (
		item.volume_monitored && item.issue_monitored ? 'Monitored' : 'Unmonitored'
	);

	row.innerHTML = `
		<td></td>
		<td><a></a></td>
		<td></td>
		<td></td>
	`;
	row.children[0].innerText = item.date || 'Unknown';
	const link = row.querySelector('a');
	link.href = `${url_base}/volumes/${item.volume_id}`;
	link.innerText = `${item.volume_title} (${item.year || 'Unknown'})`;
	row.children[2].innerText = `#${item.issue_number}${item.issue_title ? ` - ${item.issue_title}` : ''}`;
	row.children[3].innerText = status;
	document.querySelector('#calendar-items').appendChild(row);
};

function addCalendarPullRow(item) {
	const row = document.createElement('tr');
	row.innerHTML = `
		<td></td>
		<td></td>
		<td></td>
		<td></td>
	`;
	row.children[0].innerText = item.release_date || 'Unknown';
	row.children[1].innerText = item.series;
	row.children[2].innerText = `#${item.issue_number || '?'}${item.title ? ` - ${item.title}` : ''}`;
	row.children[3].innerText = item.volume_id ? `Matched (${item.match_confidence}%)` : 'Unmatched';
	document.querySelector('#calendar-pull-items').appendChild(row);
};

function loadCalendar(api_key) {
	fetchAPI('/calendar', api_key, {days: 90})
		.then(json => {
			document.querySelector('#calendar-items').innerHTML = '';
			document.querySelector('#calendar-pull-items').innerHTML = '';
			document.querySelector('#calendar-empty').classList.add('hidden');
			document.querySelector('#calendar-pull-empty').classList.add('hidden');
			const items = json.result.items;
			document.querySelector('#calendar-summary').innerText = `${items.length} issue(s) in the next 90 days`;
			if (!items.length)
				document.querySelector('#calendar-empty').classList.remove('hidden');
			else
				items.forEach(addCalendarRow);

			const pull_items = json.result.pull_list_items;
			const pull_list = json.result.pull_list || {};
			const provider_label = `${pull_list.enabled_providers || 0} provider(s) enabled`;
			document.querySelector('#calendar-pull-summary').innerText =
				`${pull_items.length} pull-list item(s), ${provider_label}`;
			if (!pull_items.length)
				document.querySelector('#calendar-pull-empty').classList.remove('hidden');
			else
				pull_items.forEach(addCalendarPullRow);
		});
};

usingApiKey().then(api_key => {
	const syncButton = document.querySelector('#calendar-sync-button');
	syncButton.onclick = event => {
		event.target.disabled = true;
		event.target.innerText = 'Sync queued…';
		sendAPI('POST', '/system/tasks', api_key, {}, {cmd: 'sync_import_lists'})
			.then(() => {
				event.target.innerText = 'Sync Import Lists';
				event.target.disabled = false;
				setTimeout(() => loadCalendar(api_key), 1500);
			});
	};
	loadCalendar(api_key);
});
