var CampBoard = CampBoard || {}

CampBoard.ws_init = function(){

	this.KEEP_ALIVE_INTERVAL = 30000;
		
	this.keepAliveReply = 0;

	this.__ws_init = function() {
		this.ws = $.gracefulWebSocket("ws://ubuntuvm:8888/campsocket/", {fallbackSendURL: "http://ubuntuvm:8080/poll/", fallbackPollURL: "http://ubuntuvm:8080/poll/", fallbackPollInterval: 5000})
		//new WebSocket("ws://ubuntuvm:8888/campsocket/");
		
		this.ws.onopen = function(){
			console.log("Registering")
			console.log((this.send("Register: " + document.URL)?"Sent":"Unsent"));
		}
		
		this.ws.onmessage = function(msg) {
			console.log("Received");
			CampBoard.parse_message(msg['data']);
		}
		
		this.ws.onerror = function(textStatus, e) {
			console.log("Error")
			console.log(textStatus);
			console.log(e)
		}

	}
	this.__ws_init();

	// Set up keep-alive ping
	this.keepAlive = setInterval(function() {
		console.log("keepAlive");
		
		if(!CampBoard.ws.send("p")) {
			console.log("Restarting WebSocket");
			CampBoard.__ws_init();
		}
		else {
			CampBoard.keepAliveReply = (new Date()).getTime(); // Record time of last successful send
		}

	}, CampBoard.KEEP_ALIVE_INTERVAL); // Ping each KEEP_ALIVE_INTERVAL sessions
	
}

CampBoard.parse_recent_tweets = function(data) {
	rts = data['recent_tweets']
	for(var i=0; i<rts.length; ++i) {
		var html = "<li><div class='tweet'>"
		html += "<a class='tweet-image' href='http://twitter.com/" + rts[i]['user']['screen_name'] + "'><img height='48px' width='48px' src='" + rts[i]['user']['profile_image_url'] + "' alt='@" + rts[i]['user']['screen_name'] + "' title='@" + rts[i]['user']['screen_name'] + "'></a>";
		html +=	"<p class='tweet-text'>" + rts[i]['text'] + "</p></div>";
		html += "<small class='tweet-permalink' target='_blank'><a href='http://twitter.com/" + rts[i]['user']['screen_name'] + "/status/" + rts[i]['id'] + "/'>permalink</a></small>"; 
		html += "</li>";
		
		if($('#recent-tweets > .placeholder:first-child').length == 1) {
			$(html).insertBefore($('#recent-tweets .placeholder:first-child'));
			$('#recent-tweets .placeholder').remove();
		}
		else {
			$(html).insertBefore($('#recent-tweets li:first-child'))
		}			
	}
}

CampBoard.parse_sessions = function(data) {
	var sess = data['sessions'];
	if(sess instanceof Object) {
		for(var i in sess) {
			// sess[i][0] is the session name
			// sess[i][1] is the cumulative vote count, or the 'DEL' instruction
			var sess_format = "<h2 class='stats-label session-title'><a href='/session/" + sess[i][0] + "/' title='" + sess[i][0] + "'>#" + sess[i][0] + "</a></h2>  <span class='session-count stats-value clearfix'>+" + sess[i][1] + "</span>";
			if($('#session-' + sess[i][0]).length == 0) { // Listing for session does not exist yet
				var html = "<li class='session' id='session-" + sess[i][0] + "'>"; // So we have to create our own <li>
				html += sess_format;
				html += "</li>";
				
				if($('#session-stats-list > .placeholder:first-child').length == 1) { // .. and place it in front of the placeholder if necessary
					$(html).insertBefore($('#session-stats-list > .placeholder:first-child'));
					$('#session-stats-list > .placeholder').remove();
				}
				else {
					var inserted = false;
					$('#session-stats-list li').each(function() {
						var v = $(this).children('.stats-value').eq(0).html();
						v = parseInt(v.substring(1, v.length));
						
						if(v < sess[i][1]) {
							$(html).insertBefore($(this));
							inserted = true;
						}
					})
					
					if(!inserted) {
						$(html).insertAfter($('session-stats-list li:last-child'));
					}

				}
			}
			else {
				if(sess[i][1] == 'DEL') {
					$('#session-' + sess[i][0]).remove()

					// Re-insert the placeholder if there are no more sessions left
					if($('#session-stats-list > .session').length ==0){
						$('#session-stats-list').append($('<li class="placeholder">None yet.</li>'));
					}
				}
				else {
					$('#session-' + sess[i][0]).eq(0).html(sess_format); // Otherwise we just substitute the contents of the appropriate <li>
				}
			}
		}
	}
}

CampBoard.parse_channel = function(data) {
	if(data['votes']) {
		if($('#session-votes-stats .placeholder') && (data['votes']['positive'] > 0 || data['votes']['negative'] > 0)) { // No votes yet, so we create our listing
			// Create the positive listing
			var html = '<li class="session-vote"><h2 class="session-vote-label stats-label">Positive</h2> <span id="session-vote-positive" class="session-vote-count stats-value">' + data['votes']['positive'] + '</span></li>';
			$(html).insertBefore($('#session-votes-stats .placeholder'));
			
			// Create the negative listing
			html = '<li class="session-vote"><h2 class="session-vote-label stats-label">Negative</span></h2> <span id="session-vote-negative" class="session-vote-count stats-value">' + data['votes']['negative'] + '</span></li>';
			$(html).insertBefore($('#session-votes-stats .placeholder'));
			
			$('#session-votes-stats .placeholder').remove();

			// Insert the graph
			if($('#session-graph .placeholder')) { // If the vote counts were 0, but now they aren't..
				// .. then insert the graph image
				$('#session-graph').html('<img src="http://chart.apis.google.com/chart?chxs=0,676767,15&chxt=x&chs=300x200&cht=p&chco=5B9DC8&chd=t:' + data['votes']['positive'] + ',' + data['votes']['negative'] + '&chp=0.628&chl=Yes|No" height="200" width="300">'); // Ugly, ugly non-multiline Javascript strings
			}

		}
	
		$('#session-vote-positive').html(data['votes']['positive'])
		$('#session-vote-negative').html(data['votes']['negative'])
		$('#session-votes-total').html(data['votes']['positive'] + data['votes']['negative'])
		$('#session-tweet-count').html(data['total_tweets'])
	}

}

CampBoard.parse_broadcast = function(data) {
	var channel = data['channel'] || null;		
	$.jGrowl(data['broadcast_message'], {header: (channel)?"#" + channel+" Notice":"BarCampSG6 Notice" });
}

CampBoard.parse_message = function(d) {
	console.log("Parsing!")
	console.log(d)
	try {
		var data = $.parseJSON(d); //JSON.parse(data); // Extract the data

	
		if(data['total_tweets']) {
			$('#total-tweets').html(data['total_tweets']);
		}
		
		if(data['uniques']) {
			$('#unique-tweeters').html(data['uniques'])
		}

		if(data['sessions_number'] >= 0) {
			$('#total-sessions').html(data['sessions_number'])
		}

		
		if(data['recent_tweets']) {
			CampBoard.parse_recent_tweets(data);
		}
		
		if(data['sessions']) {
			CampBoard.parse_sessions(data);
		}	
		
		// If we're on a session page
		if(data['channel'] && document.URL.match(/\/session\/(\w+)/)[1] == data['channel']) {
			CampBoard.parse_channel(data);
		}
		
		if(data['broadcast_message']) {
			CampBoard.parse_broadcast(data);
		}
	}
	catch(e) {
		console.log(e)
		//alert(e)
		//alert("Uhoh");
	}
}


CampBoard.send_message = function(method, channel, data) {

	// Trap defaults
	channel = channel || '';
	
	// Fail with improper params
	if(!method){ return false; }
	
	if(!this.ws.send(JSON.stringify({'method':method, 'channel':channel, 'data':data}))) {
		$.jGrowl('Error in sending', {header: 'Error'});
	}
	
}

/**
 * Tweaked from: http://www.milesj.me/resources/snippet/13
 * Transform text into a URL slug: spaces turned into dashes, remove non alnum
 * @param string text
 */
CampBoard.slugify = function(text) {
	text = text.replace(/[^-a-zA-Z0-9,&\s]+/ig, '');
	text = text.replace(/-/gi, "_");
	text = text.replace(/\s/gi, "-");
	return text.toLowerCase();
}

if(jQuery) {
	$(window).load(function() {
		CampBoard.ws_init();
	})
	
	$(window).unload(function(){
		CampBoard.ws.send("Close");
		CampBoard.ws.close();
	})
}
