function addStoryArcCard(arc) {
	const card = document.createElement('article');
	card.className = 'arr-card';
	card.innerHTML = `
		<h2></h2>
		<p class="arr-status"></p>
		<p></p>
		<ol class="arr-reading-list"></ol>
	`;
	card.querySelector('h2').innerText = arc.title;
	card.querySelector('.arr-status').innerText = arc.monitored ? 'Monitored' : 'Unmonitored';
	card.querySelector('p').innerText = `${arc.issues.length} issue(s) in reading order`;
	const list = card.querySelector('.arr-reading-list');
	arc.issues.forEach(issue => {
		const item = document.createElement('li');
		const issueName = issue.matched_issue_number
			? `#${issue.matched_issue_number}`
			: (issue.title || 'Unmatched issue');
		item.innerText = `${issueName} — ${issue.volume_title || 'Unmatched volume'}`;
		list.appendChild(item);
	});
	document.querySelector('#story-arc-cards').appendChild(card);
};

function parseIssueLines(raw) {
	return raw.split('\n')
		.map(line => line.trim())
		.filter(line => line)
		.map((line, index) => {
			const parts = line.split(',').map(part => part.trim());
			return {
				reading_order: index + 1,
				series: parts[0] || '',
				issue_number: parts[1] || '',
				title: parts.slice(2).join(', ')
			};
		});
};

function loadStoryArcs(api_key) {
	const cards = document.querySelector('#story-arc-cards');
	cards.innerHTML = '';
	document.querySelector('#story-arcs-empty').classList.add('hidden');
	fetchAPI('/storyarcs', api_key)
		.then(json => {
			const arcs = json.result;
			if (!arcs.length) {
				document.querySelector('#story-arcs-empty').classList.remove('hidden');
				return;
			};
			arcs.forEach(addStoryArcCard);
		});
};

usingApiKey().then(api_key => {
	const form = document.querySelector('#story-arc-form');
	form.onsubmit = event => {
		event.preventDefault();
		const payload = {
			title: document.querySelector('#story-arc-title').value,
			description: document.querySelector('#story-arc-description').value,
			monitored: document.querySelector('#story-arc-monitored').checked,
			issues: parseIssueLines(document.querySelector('#story-arc-issues').value)
		};
		sendAPI('POST', '/storyarcs', api_key, {}, payload)
			.then(response => response.json())
			.then(() => {
				form.reset();
				document.querySelector('#story-arc-monitored').checked = true;
				loadStoryArcs(api_key);
			});
	};
	loadStoryArcs(api_key);
});
