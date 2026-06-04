function fillSettings(api_key) {
	fetchAPI('/settings', api_key)
	.then(json => {
		document.querySelector('#date-type-input').value = json.result.date_type;
	});
};

function saveSettings(api_key) {
	document.querySelector("#save-button p").innerText = 'Saving';
	const data = {
		'date_type': document.querySelector('#date-type-input').value
	};
	sendAPI('PUT', '/settings', api_key, {}, data)
	.then(response => response.json())
	.then(json => {
		document.querySelector("#save-button p").innerText = 'Saved';
	})
	.catch(e => {
		document.querySelector("#save-button p").innerText = 'Failed';
		console.log(e);
	});
};


function writeAllMetadata(api_key) {
	const buttonText = document.querySelector('#write-all-metadata-button p');
	buttonText.innerText = 'Queued';
	sendAPI('POST', '/system/tasks', api_key, {}, {cmd: 'write_all_metadata'})
	.then(response => response.json())
	.then(json => {
		buttonText.innerText = json.error ? 'Failed' : 'Queued';
	})
	.catch(e => {
		buttonText.innerText = 'Failed';
		console.log(e);
	});
};

// code run on load

usingApiKey()
.then(api_key => {
	fillSettings(api_key);
	document.querySelector('#save-button').onclick = e => saveSettings(api_key);
	document.querySelector('#write-all-metadata-button').onclick = e => writeAllMetadata(api_key);
});
