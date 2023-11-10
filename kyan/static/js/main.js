document.addEventListener("DOMContentLoaded", function(event) { // wait for content to load because this script is above the link
	document.getElementById('themeToggle').addEventListener('click', function(e) { // listen for click event
		e.preventDefault(); // keep link from default action, which going to top of the page
		toggleDarkMode();   // toggle theme
	});
	// needs to be done here as <body> is not available when the script in the head runs
	if (typeof(Storage) !== 'undefined' && localStorage.getItem('theme') === 'dark')
		document.body.classList.add('dark');
});


// Credit: https://www.abeautifulsite.net/whipping-file-inputs-into-shape-with-bootstrap-3
// We can attach the `fileselect` event to all file inputs on the page
$(document).on('change', ':file', function() {
	var input = $(this),
		numFiles = input.get(0).files ? input.get(0).files.length : 1,
		label = input.val().replace(/\\/g, '/').replace(/.*\//, '');
	input.trigger('fileselect', [numFiles, label]);
});


// We can watch for our custom `fileselect` event like this
$(document).ready(function() {
	var dropZone = $('#upload-drop-zone'),
		fileWarning = $('<div/>').html('Invalid file selected. Please select a torrent file.')
			.css({  id: 'file-warning', class: 'alert alert-warning text-center',
					role: 'alert', width: $('.form-group:first').width() + 'px' })
			.hide().insertAfter(dropZone);

	$('#torrent_file:file').on('fileselect', function(event, numFiles, label) {
		var input = $(this).parent().parent().find('input:text'),
			log = numFiles > 1 ? numFiles + ' files selected' : label;

		if (label.endsWith('.torrent')) {
			fileWarning.fadeOut('fast');
		} else {
			fileWarning.fadeIn('fast');
			input.val('');
			return false;
		}

		if (input.length) {
			input.val(log);
		} else {
			if (log) alert(log);
		}
	});

	// Avatar
	$('#image_file:file').on('fileselect', function(event, numFiles, label) {
		var input = $(this).parent().parent().find('input:text');
		input.val(label);
	});

	// Drag & Drop zone for upload page
	$('body').on('dragenter', function(event) {
		event.preventDefault();
		dropZone.css({ 'visibility': 'visible', 'opacity': 1 });
	});

	dropZone.on('dragleave', function(event) {
		event.preventDefault();
		$(this).css({ 'visibility': 'hidden', 'opacity': 0 });
	});

	dropZone.on('dragover', function(event) {
		event.preventDefault();
	});

	dropZone.on('drop dragdrop', function(event) {
		event.preventDefault();
		var files = event.originalEvent.dataTransfer.files;
		var torrent_file_input = $('#torrent_file');
		torrent_file_input[0].files = files;
		// Manually trigger event?
		torrent_file_input.trigger('fileselect', [
			files ? files.length : 0,
			torrent_file_input.val().replace(/\\/g, '/').replace(/.*\//, '')
		]);
		$(this).css({ 'visibility': 'hidden', 'opacity': 0 });
	});

	// Collapsible file lists
	$('.torrent-file-list a.folder').click(function(e) {
		e.preventDefault();
		$(this).blur().children('i').toggleClass('fa-folder-open fa-folder');
		$(this).next().stop().slideToggle(250);
	});

	// Comment editing below
	$('.edit-comment').click(function(e) {
		e.preventDefault();
		$(this).closest('.comment').toggleClass('is-editing');
	});

	$('[data-until]').each(function() {
		var $this = $(this),
			text = $(this).text(),
			until = $this.data('until');

		var displayTimeRemaining = function() {
			var diff = Math.max(0, until - (Date.now() / 1000) | 0),
				min = Math.floor(diff / 60),
				sec = diff % 60;
			$this.text(text + ' (' + min + ':' + ('00' + sec).slice(-2) + ')');
		};

		displayTimeRemaining();
		setInterval(displayTimeRemaining, 1000);
	});

	$('.edit-comment-box').submit(function(e) {
		e.preventDefault();

		var $this = $(this),
			$submitButton = $this.find('[type=submit]').attr('disabled', 'disabled'),
			$waitIndicator = $this.find('.edit-waiting').show()
			$errorStatus = $this.find('.edit-error').empty();

		$.ajax({
			type: $this.attr('method'),
			url: $this.attr('action'),
			data: $this.serialize()
		}).done(function(data) {
			var $comment = $this.closest('.comment');
			$comment.find('.comment-content').html(markdown.render(data.comment));
			$comment.toggleClass('is-editing');
		}).fail(function(xhr) {
			var error = xhr.responseJSON && xhr.responseJSON.error || 'An unknown error occurred.';
			$errorStatus.text(error);
		}).always(function() {
			$submitButton.removeAttr('disabled');
			if (window.grecaptcha) {
				window.grecaptcha.reset();
			}
			$waitIndicator.hide();
		});
	})
});

function _format_time_difference(seconds) {
	var units = [
		["year", 365*24*60*60],
		["month", 30*24*60*60],
		["week",  7*24*60*60],
		["day",     24*60*60],
		["hour",      60*60],
		["minute",       60],
		["second",        1]
	];
	var suffix = " ago";
	var prefix = "";
	if (seconds < 0) {
		suffix = "";
		prefix = "After ";
		seconds = -seconds;
	} else if (Math.abs(seconds) < 15) {
		return "Just now"
	}

	var parts = [];
	for (var i = 0; i < units.length; i++) {
		var scale = units[i];

		var m = (seconds / scale[1]) | 0;

		if (m > 0) {
			// N unit(s)
			parts.push( m.toString() + " " + scale[0] + (m == 1 ? "" : "s") );
			seconds -= m*scale[1];
		}
	}
	// Use the... first three parts, that's enough detail
	parts = parts.slice(0, 3);
	return prefix + parts.join(" ") + suffix;
}
function _format_date(date, show_seconds) {
	var pad = function (n) { return ("00" + n).slice(-2); }
	var ymd = date.getFullYear() + "-" + pad(date.getMonth()+1) + "-" + pad(date.getDate());
	var hm = pad(date.getHours()) + ":" + pad(date.getMinutes());
	var s = show_seconds ? ":" + pad(date.getSeconds()) : ""
	return ymd + " " + hm + s;
}

// Add title text to elements with data-timestamp attribute
document.addEventListener("DOMContentLoaded", function(event) {
	var now_timestamp = (Date.now() / 1000) | 0; // UTC timestamp in seconds

	var timestamp_targets = document.querySelectorAll('[data-timestamp]');
	for (var i = 0; i < timestamp_targets.length; i++) {
		var target = timestamp_targets[i];
		var torrent_timestamp = parseInt(target.getAttribute('data-timestamp'));
		var swap_flag = target.getAttribute('data-timestamp-swap') != null;
		var title_flag = target.getAttribute('data-timestamp-title') != null;

		if (torrent_timestamp) {
			var timedelta = now_timestamp - torrent_timestamp;

			var formatted_date = _format_date(new Date(torrent_timestamp*1000), swap_flag);
			var formatted_timedelta = _format_time_difference(timedelta);
			if (swap_flag) {
				target.setAttribute('title', formatted_date);
				if (!title_flag) {
					target.innerText = formatted_timedelta;
				}
			} else {
				target.setAttribute('title', formatted_timedelta);
				if (!title_flag) {
					target.innerText = formatted_date;
				}
			}
		}
	};

	var header_date = document.querySelector('.hdr-date');
	if (header_date) {
		header_date.setAttribute('title', 'In local time');
	}
});

var markdownOptions = {
	html : false,
	breaks : true,
	linkify: true,
	typographer:  true
}
var markdown = window.markdownit(markdownOptions);
markdown.renderer.rules.table_open = function (tokens, idx) {
	// Format tables nicer (bootstrap). Force auto-width (default is 100%)
	return '<table class="table table-striped table-bordered" style="width: auto;">';
}
var defaultRender = markdown.renderer.rules.link_open || function(tokens, idx, options, env, self) {
	return self.renderToken(tokens, idx, options);
};
markdown.renderer.rules.link_open = function (tokens, idx, options, env, self) {
	tokens[idx].attrPush(['rel', 'noopener nofollow noreferrer']);
	return defaultRender(tokens, idx, options, env, self);
}

// Override the image rule.
const defaultImageRender = markdown.renderer.rules.image || function (tokens, idx, options, env, self) {
	return self.renderToken(tokens, idx, options);
};
markdown.renderer.rules.image = function (tokens, idx, options, env, self) {
	function getPhotonURL(inURL) {
		// Basic hash to distribute out to the Photon servers.
		let hash = 0;
		for (let i = 0; i < inURL.length; i++) {
			const char = inURL.charCodeAt(i);
			hash = (hash << 5) - hash + char;
			hash &= hash;
		}

		const urlWhitelist = ['discord.com', 'discordapp.com', 'discordapp.net', 'google.com', 'googleusercontent.com', 'gstatic.com', 'imgur.com', 'naver.net', 'nocookie.net', 'redd.it', 'twimg.com', 'wordpress.com', 'weserv.nl', 'wp.com', 'wsrv.nl'];

		var photonURL;

		if (typeof(window.URL) != "function") {
			// Always pass through for ancient browsers like IE.
			photonURL = inURL;
		} else {
			let urlObj = new URL(inURL, location.href);

			// Get host.
			var urlHost = urlObj.hostname.split('.').slice(-2).join('.');

			// Check if host is on the WP whitelist, or is a data URI.
			if (urlWhitelist.includes(urlHost) || urlObj.protocol == 'data:') {
				// Whitelisted URLs get passed through.
				photonURL = inURL;
			} else if (urlObj.username || urlObj.password || urlObj.port || (urlObj.search && !urlObj.search.match(/^\?\d*$/))) {
				// URL would break with Photon. Use wsrv.nl instead.
				// The regex check above is to ignore "cachebuster" query strings.
				// The &n=-1 below is to enable support for animated images.
				photonURL = 'https://wsrv.nl/?url=' + encodeURIComponent(inURL) + '&n=-1';
			} else {
				// Get URL into format expected by Photon.
				photonURL = 'https://i' + (Math.abs(hash) % 3) + '.wp.com/' + urlObj.host + urlObj.pathname;

				// Set SSL where applicable.
				if (urlObj.protocol == 'https:') {
					photonURL += '?ssl=1';
				}
			}
		}

		return photonURL;
	}

	// Get the current token.
	let token = tokens[idx];
	let aIndex = token.attrIndex('src');

	// Get the current image URL.
	const imageURL = (aIndex < 0) ? null : token.attrs[aIndex][1];

	// Replace image URL if found.
	if (window.markdown_proxy_images && imageURL) {
		token.attrs[aIndex][1] = getPhotonURL(imageURL);
	}

	// Pass token to default renderer.
	return defaultImageRender(tokens, idx, options, env, self);
}

// Initialise markdown editors on page
document.addEventListener("DOMContentLoaded", function() {
	var markdownEditors = Array.prototype.slice.call(document.querySelectorAll('.markdown-editor'));

	markdownEditors.forEach(function (markdownEditor) {
		var fieldName = markdownEditor.getAttribute('data-field-name');

		var previewTabSelector = '#' + fieldName + '-preview-tab';
		var targetSelector = '#' + fieldName + '-markdown-target';
		var sourceSelector = markdownEditor.querySelector('.markdown-source');

		var previewTabEl = markdownEditor.querySelector(previewTabSelector);
		var targetEl = markdownEditor.querySelector(targetSelector);

		previewTabEl.addEventListener('click', function () {
			var rendered = markdown.render(sourceSelector.value.trim());
			targetEl.innerHTML = rendered;
		});
	});
});

// Render markdown from elements with "markdown-text" attribute
document.addEventListener("DOMContentLoaded", function() {
	var markdownTargets = document.querySelectorAll('[markdown-text],[markdown-text-inline]');
	for (var i = 0; i < markdownTargets.length; i++) {
		var target = markdownTargets[i];
		var rendered;
		var markdownSource = htmlDecode(target.innerHTML);
		if (target.attributes["markdown-no-images"]) {
			markdown.disable('image');
		} else {
			markdown.enable('image');
		}
		if (target.attributes["markdown-text-inline"]) {
			rendered = markdown.renderInline(markdownSource);
		} else {
			rendered = markdown.render(markdownSource);
		}
		target.innerHTML = rendered;
	}
});

// Info bubble stuff
document.addEventListener("DOMContentLoaded", function() {
	var bubble = document.getElementById('infobubble');
	if (bubble && Number(localStorage.getItem('infobubble_dismiss_ts')) < Number(bubble.dataset.ts)) {
		bubble.removeAttribute('hidden');
	}
	$('#infobubble').on('close.bs.alert', function () {
		localStorage.setItem('infobubble_dismiss_ts', bubble.dataset.ts);
	})
});

// Decode HTML entities (&gt; etc), used for decoding comment markdown from escaped text
function htmlDecode(input){
	var e = document.createElement('div');
	e.innerHTML = input;
	return e.childNodes[0].nodeValue;
}

//
// This is the unminified version of the theme changer script in the layout.html @ line: 21
// ===========================================================
// if (typeof(Storage) !== 'undefined') {
// 	var bsThemeLink = document.getElementById('bsThemeLink');

// 	if (localStorage.getItem('theme') === 'dark') {
// 		setThemeDark();
// 	}

// 	function toggleDarkMode() {
// 		if (localStorage.getItem('theme') === 'dark') {
// 			setThemeLight();
// 		} else {
// 			setThemeDark();
// 		}
// 	}

// 	function setThemeDark() {
// 		bsThemeLink.href = '/static/css/bootstrap-dark.min.css';
// 		localStorage.setItem('theme', 'dark');
// 		if (document.body !== null)
// 			document.body.classList.add('dark');
// 	}

// 	function setThemeLight() {
// 		bsThemeLink.href = '/static/css/bootstrap.min.css';
// 		localStorage.setItem('theme', 'light');
// 		if (document.body !== null)
// 			document.body.classList.remove('dark');
// 	}
// }