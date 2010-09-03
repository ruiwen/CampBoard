var CampBoard = CampBoard || {}

CampBoard.ws_init = function(){
	this.ws = $.gracefulWebSocket("ws://ubuntuvm:8888/campsocket/", {fallbackSendURL: "http://ubuntuvm:8080/poll/", fallbackPollURL: "http://ubuntuvm:8080/poll/", fallbackPollInterval: 5000})
	//new WebSocket("ws://ubuntuvm:8888/campsocket/");
	
	this.ws.onopen = function(){
		console.log("Registering")
		console.log((this.send("Register: " + document.URL)?"Sent":"Unsent"));
	}
	
	this.ws.onmessage = function(msg) {
		//alert("Received");
		console.log("Received");
		console.log(msg.data);
		
		CampBoard.parse_message(msg['data']);
	}
	
	this.ws.onerror = function(textStatus, e) {
		console.log("Error")
		console.log(textStatus);
		console.log(e)
	}
}

CampBoard.parse_message = function(d) {
	console.log("Parsing!")
	console.log(d)
	try {
		var data = $.parseJSON(d); //JSON.parse(data); // Extract the data

	
		if(data['total_tweets']) {
			$('#total-tweets').html(data['total_tweets']);
		}
		
		if(data['unique_tweeters']) {
			$('#unique-tweeters').html(data['unique_tweeters'])
		}

		if(data['sessions_number'] >= 0) {
			$('#total-sessions').html(data['sessions_number'])
		}

		
		if(data['recent_tweets']) {
			rts = data['recent_tweets']
			for(var i=0; i<rts.length; ++i) {
				var html = "<li><div class='tweet'>"
				html += "<a class='tweet-image' href='http://twitter.com/" + rts[i]['user']['screen_name'] + "'><img src='" + rts[i]['user']['profile_image_url'] + "'></a>";
				html +=	"<p class='tweet-text'>" + rts[i]['text'] + "</p></div>";
				html += "<small class='tweet-permalink' target='_blank'><a href='http://twitter.com/" + rts[i]['user']['screen_name'] + "/status/" + rts[i]['id'] + "/'>permalink</a></small>"; 
				html += "</li>";
				
				if($('#recent-tweets > .placeholder:first-child').length == 1) {
					$(html).insertBefore($('#recent-tweets > .placeholder:first-child'));
					$('#recent-tweets > .placeholder').remove();
				}
				else {
					$(html).insertBefore($('#recent-tweets > li:first-child'))
				}			
			}
		}
		
		if(data['sessions']) {
			var sess = data['sessions'];
			if(sess instanceof Object) {
				for(var i in sess) {
					var sess_format = "<h2><span class='stats-label session-title'><a href='/session/" + i + "/'>#" + i + "</a></span>  <span class='session-count stats-value'>+" + sess[i] + "</span></h2>";
					if($('#session-' + i).length == 0) { // Listing for session does not exist yet
						var html = "<li class='session' id='session-" + i + "'>"; // So we have to create our own <li>
						html += sess_format;
						html += "</li>";
						
						if($('#session-stats-list > .placeholder:first-child').length == 1) { // .. and place it in front of the placeholder if necessary
							$(html).insertBefore($('#session-stats-list > .placeholder:first-child'));
							$('#session-stats-list > .placeholder').remove();
						}
						else {
							$(html).insertBefore($('#session-stats-list > li:first-child'));
						}
					}
					else {
						if(sess[i] == 'DEL') {
							$('#session-' + i).remove()
							
							// Re-insert the placeholder if there are no more sessions left
							if($('#session-stats-list > .session').length ==0){
								$('#session-stats-list').append($('<li class="placeholder">None yet.</li>'));
							}
						}
						else {
							$('#session-' + i).eq(0).html(sess_format); // Otherwise we just substitute the contents of the appropriate <li>
						}
					}
				}
			}
		}	
		
		
		// If we're on a session page
		if(data['channel'] && document.URL.match(/\/session\/(\w+)/)[1] == data['channel']) {
			if(data['votes']) {
				$('#session-vote-positive').html(data['votes']['positive'])
				$('#session-vote-negative').html(data['votes']['negative'])
				$('#session-votes-total').html(data['votes']['positive'] + data['votes']['negative'])
				$('#session-tweet-count').html(data['tweet_count'])
			}
		}
		
	
	
		if(data['broadcast_message']) {
			$('#broadcast').html(data['broadcast_message']);
			$('#broadcast').show()
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
	
	this.ws.send(JSON.stringify({'method':method, 'channel':channel, 'data':data}));
	
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
