////////////////////////////////////////////////////////////////////////////////
// Initialization
////////////////////////////////////////////////////////////////////////////////
const myPrice = document.getElementById('myPrice');
const myQuantity = document.getElementById('myQuantity');
const myProposal = document.getElementById('myProposal');
const otherProposal = document.getElementById('otherProposal');

const btnChat = document.getElementById("btn-chat");
const btnOffer = document.getElementById("btn-offer");
const btnAccept = document.getElementById('btnAccept');
const btnStopRoom = document.getElementById('btn-stop-room');

const personaAutoEnabled = js_vars.persona_auto === true;
const personaScript = js_vars.persona_script || [];
let personaFinished = false;
let personaScriptIndex = 0;
let lastBotOffer = null;
let repostedLastOffer = false;
let personaLastBotTurnAt = 0;
let personaBusyUntil = 0;
let personaBlockStartedAt = 0;
let botOfferCount = 0;
const PERSONA_REPLY_DELAY_MS = 750;
const PERSONA_TICK_MS = 400;
const PERSONA_BLOCK_WATCHDOG_MS = 60000;

// Registered first so a later init failure cannot stop the simulation.
if (personaAutoEnabled) {
  setInterval(personaTick, PERSONA_TICK_MS);
}

document.addEventListener('DOMContentLoaded', () => {
  personaCreateStatusBadge();
  personaLog('auto =', personaAutoEnabled,
      '| scripted turns =', personaScript.length);

  if (personaAutoEnabled) {
    const negotiateTab = document.getElementById('pills-negotiate-tab');
    if (negotiateTab) {
      negotiateTab.click();
    }
  }

  if (js_vars.can_stop_room === true) {
    const stopWrap = document.getElementById('stop-room-wrap');
    if (stopWrap) {
      stopWrap.style.display = 'block';
    }
    if (js_vars.stop_requested === true) {
      markStopRoomRequested(null);
    }
  }
  if (js_vars.bot_opponent === true) {
    // Disable send buttons for bot opponent
    btnChat.disabled = true;
    myPrice.disabled = true;
    myQuantity.disabled = true;

    // Start the negotiations, needed here for event loop
    setTimeout(() => {
      liveSend({'type': 'initial'});
    }, 1000);
  }

  try {
    receiveMessage(js_vars.messages || []);
    receiveoffers(js_vars.offers || []);
  } catch (err) {
    console.error('[persona] init render failed', err);
    personaSetStatus('init error: ' + err.message);
  }

  // Always disable offer button on (re)loading of page
  btnOffer.disabled = true;
  if (!otherProposal.innerHTML.includes('none')) {
    btnAccept.disabled = false;
  }

  setInterval(() => {
    liveSend({'type': 'ping'});
  }, 1000);
});

function liveRecv(data) {
  if (personaAutoEnabled) {
    personaLog('liveRecv keys:', Object.keys(data).join(','));
  }
  if ('finished' in data) {
    personaFinished = true;
    document.getElementById('form').submit();
  }
  if ('chat' in data) {
    receiveMessage(data.chat);
  }
  if ('offers' in data) {
    receiveoffers(data.offers);
  }
  if ('unblock' in data) {
    console.log("UNBLOCK received!");
    blockUnblock(false);
  }
  if ('stopping' in data) {
    markStopRoomRequested(data.stopping);
  }
}

////////////////////////////////////////////////////////////////////////////////
// Stop the room after the current round
////////////////////////////////////////////////////////////////////////////////
function stopRoom() {
  if (!confirm('Stop the room after this negotiation round finishes?\n\n' +
      'The current round plays out and its data is saved. No further ' +
      'rounds will start.')) {
    return;
  }
  liveSend({'type': 'stop_room'});
  if (btnStopRoom) {
    btnStopRoom.disabled = true;
  }
}

function markStopRoomRequested(round) {
  if (btnStopRoom) {
    btnStopRoom.disabled = true;
  }
  const status = document.getElementById('stop-room-status');
  if (status) {
    status.textContent = round
        ? ' Stopping after round ' + round + '.'
        : ' Stop already requested.';
  }
}

////////////////////////////////////////////////////////////////////////////////
// Persona auto-counterpart (simulation rooms 107/108)
////////////////////////////////////////////////////////////////////////////////
function personaLog() {
  console.log.apply(console, ['[persona]'].concat(Array.from(arguments)));
}

// On-page status so the simulation can be diagnosed without the dev console.
function personaCreateStatusBadge() {
  const badge = document.createElement('div');
  badge.id = 'persona-status';
  badge.style.cssText =
      'position:fixed;bottom:8px;right:8px;z-index:9999;padding:6px 10px;' +
      'font:12px/1.4 monospace;border-radius:4px;color:#fff;max-width:340px;' +
      'background:' + (personaAutoEnabled ? '#1b6e3c' : '#8a1f1f') +
      ';cursor:pointer';
  badge.title = 'Click to force the next scripted turn';
  badge.addEventListener('click', personaForce);
  document.body.appendChild(badge);
  personaSetStatus(personaAutoEnabled
      ? 'waiting for first bot message'
      : 'DISABLED (persona_auto=false)');
}

function personaSetStatus(text) {
  const badge = document.getElementById('persona-status');
  if (badge) {
    badge.textContent = 'persona ' + personaScriptIndex + '/' +
        personaScript.length + ' - ' + text;
  }
}

// A bot turn is pending a reply when this is non-zero.
function personaNoteBotTurn(source) {
  if (!personaAutoEnabled || personaFinished) {
    return;
  }
  personaLog('bot turn detected via', source);
  personaLastBotTurnAt = Date.now();
  personaSetStatus('bot turn (' + source + '), replying shortly');
}

function personaOnBotChat(messages) {
  if (!personaAutoEnabled || personaFinished) {
    return;
  }
  const last = messages[messages.length - 1];
  if (!last || String(last['nick']).indexOf('(Me)') !== -1) {
    return;
  }
  personaNoteBotTurn('chat');
}

function personaOnBotOffer() {
  personaNoteBotTurn('offer');
}

function personaSendTurn(turn) {
  personaLog('sending offer', turn.turn, turn.price, turn.quantity);
  personaSetStatus('sent offer ' + turn.price + ' x ' + turn.quantity);
  liveSend({
    'type': 'propose',
    'price': turn.price,
    'quantity': turn.quantity,
    'body': turn.message,
  });
  blockUnblock(true);
  personaBlockStartedAt = Date.now();
}

function personaCloseDeal() {
  if (lastBotOffer) {
    personaLog('script exhausted, accepting bot offer', lastBotOffer);
    personaBusyUntil = Date.now() + 10000;
    liveSend({
      'type': 'accept',
      'price': lastBotOffer.price,
      'quantity': lastBotOffer.quantity,
    });
    return;
  }
  if (!repostedLastOffer && personaScript.length > 0) {
    personaLog('script exhausted, no bot offer yet - reposting final offer');
    repostedLastOffer = true;
    personaSendTurn(personaScript[personaScript.length - 1]);
  }
}

// Single driver loop: avoids losing turns when live messages overlap.
function personaTick() {
  if (!personaAutoEnabled || personaFinished) {
    return;
  }

  const now = Date.now();
  if (now < personaBusyUntil) {
    return;
  }

  if (blockedOffer) {
    if (personaBlockStartedAt > 0 &&
        now - personaBlockStartedAt > PERSONA_BLOCK_WATCHDOG_MS) {
      personaLog('watchdog: forcing unblock after timeout');
      personaSetStatus('watchdog unblock');
      blockUnblock(false);
      personaBlockStartedAt = 0;
    }
    return;
  }

  if (personaLastBotTurnAt === 0) {
    return;
  }
  if (now - personaLastBotTurnAt < PERSONA_REPLY_DELAY_MS) {
    return;
  }

  personaLastBotTurnAt = 0;

  if (personaScriptIndex < personaScript.length) {
    const turn = personaScript[personaScriptIndex];
    personaScriptIndex += 1;
    personaSendTurn(turn);
    return;
  }

  personaCloseDeal();
}

// Manual trigger for debugging: click the badge (or call personaForce()).
function personaForce() {
  personaLog('forced step');
  personaLastBotTurnAt = 1;
  personaBusyUntil = 0;
  personaTick();
}
window.personaForce = personaForce;

////////////////////////////////////////////////////////////////////////////////
// Blocking functionality
////////////////////////////////////////////////////////////////////////////////
let blockedChat = js_vars.bot_opponent;
let blockedOffer = js_vars.bot_opponent;
let blockCount = 0;

function blockUnblock(block) {
  if (js_vars.bot_opponent !== true) {
    return;
  }

  blockedChat = btnChat.disabled = block;

  blockedOffer = block;
  if (blockedOffer === true) {
    btnOffer.disabled = true;
    myPrice.disabled = true;
    myQuantity.disabled = true;
  } else {
    myPrice.disabled = false;
    myQuantity.disabled = false;
    // Price has been entered, Quantity has been entered
    if (myPrice.value !== "" && myQuantity.value !== "") {
      btnOffer.disabled = false;
    }
  }
  myPrice.placeholder = "Price here..."
  if (!block) {
    personaBlockStartedAt = 0;
  }
}

function unblockAfterMessage() {
  if (js_vars.bot_opponent !== true) {
    return;
  }
  let nicks = chatOutput.getElementsByClassName('otree-chat__nickname');

  blockCount = 0;
  Array.from(nicks).forEach((n) => {
    blockCount += n.innerHTML.includes("(Me)");
  });

  let lastNick = nicks[nicks.length - 1].innerHTML;
  if (!lastNick.includes("(Me)")) {
    blockUnblock(false);
  }
}

function unblockBtnOffer() {
  btnOffer.disabled = !(myPrice.value.trim() !== "" && myQuantity.value.trim() !== "" && blockedOffer === false);
}

////////////////////////////////////////////////////////////////////////////////
// Bargain functionality
////////////////////////////////////////////////////////////////////////////////
myPrice.addEventListener("keydown", function (event) {
  let key = event.key;
  // Always allow Delete and Backspace
  if (["Delete", "Backspace"].includes(key)) {
    unblockBtnOffer();
    return;
  }

  // Only allow numbers and dot
  if (isNaN(parseFloat(key)) && key !== '.') {
    event.preventDefault();
    return;
  }

  // Prevent multiple decimal points
  if (key === "." && myPrice.value.includes(".")) {
    event.preventDefault();
    return;
  }

  // Prevent more than 2 decimal places
  if (myPrice.value.includes(".") && myPrice.value.split(".")[1].length >= 2) {
    event.preventDefault();
    return;
  }
  unblockBtnOffer();
});

myQuantity.addEventListener("keydown", function (event) {
  let key = event.key;
  // Always allow Delete and Backspace
  if (["Delete", "Backspace"].includes(key)) {
    unblockBtnOffer();
    return;
  }

  // Allow only numbers
  if (isNaN(parseInt(key))) {
    event.preventDefault();
    return;
  }
  unblockBtnOffer();
});

myQuantity.addEventListener("input", function () {
  // Ensure the input is an integer
  myQuantity.value = myQuantity.value.replace(/[^0-9]/g, ""); // Remove non-numeric characters

  // Enforce minimum and maximum values
  if (myQuantity.value !== "") {
    let value = parseInt(myQuantity.value);
    value = Math.max(value, js_vars.demand_min);
    myQuantity.value = Math.min(value, js_vars.demand_max);
  }
  unblockBtnOffer();
});

function sendOffer() {
  let price = parseFloat(myPrice.value);
  let quantity = parseInt(myQuantity.value);
  if (!isNaN(price) && !isNaN(quantity)) {
    liveSend({'type': 'propose', 'price': price, 'quantity': quantity})
  }
  myPrice.value = "";
  myQuantity.value = "";
  btnOffer.disabled = true;
  blockUnblock(true);
}

function sendAccept() {
  btnChat.disabled = true;
  btnOffer.disabled = true;
  btnAccept.disabled = true;

  let proposal = otherProposal.innerHTML;
  let price = parseFloat(proposal.split('<br>')[0].replace('€', ''));
  if (isNaN(price)) {
    return;
  }
  let quantity = parseInt(proposal.split('<br>')[1]);
  liveSend({'type': 'accept', 'price': price, 'quantity': quantity})
}

function receiveoffers(offers) {
  let botOffers = 0;
  offers.forEach((offer) => {
    if (offer['price'] !== null && offer['quantity'] !== null) {
      let innerHTML = `€ ${offer['price']}<br>${offer['quantity']}`;
      if (offer['idx'] === js_vars.id_in_group) {
        myProposal.innerHTML = innerHTML;
      } else {
        botOffers += 1;
        otherProposal.innerHTML = innerHTML;
        lastBotOffer = {
          price: offer['price'],
          quantity: offer['quantity'],
        };
        if (!personaAutoEnabled) {
          btnAccept.disabled = false;
        }
      }
    }
  });

  if (botOffers > botOfferCount) {
    botOfferCount = botOffers;
    personaOnBotOffer();
  }
}

////////////////////////////////////////////////////////////////////////////////
// Chat functionality
////////////////////////////////////////////////////////////////////////////////
const chatOutput = document.getElementById("chat-output");
const chatInput = document.getElementById("chat-input");

chatInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && blockedChat === false) {
    sendMessage();
  }
});

function sendMessage() {
  let body = chatInput.value;
  if (body === "") {
    return;
  }

  liveSend({'type': 'chat', 'body': body});

  chatInput.value = "";
  blockUnblock(true);
}

function receiveMessage(messages) {
  let messagesHTML = '';
  messages.forEach((message) => {
    let nick = escapeHtml(message['nick']);
    let body = escapeHtml(message['body']).replaceAll('\n', '<br>');
    messagesHTML += "<div class='otree-chat__msg'>" +
        "<span class='otree-chat__nickname'>" + nick + "</span>" +
        "<span class='otree-chat__body'>" + body + "</span>" +
        "</div>";
  });
  messagesHTML += "<div class='otree-chat__msg'>&nbsp;</div>";
  chatOutput.innerHTML = messagesHTML;
  chatOutput.scrollTo({
    top: chatOutput.scrollHeight,
    left: 0,
    behavior: "smooth",
  });
  if (messages.length > 0) {
    unblockAfterMessage();
    personaOnBotChat(messages);
  }
}

function escapeHtml(string) {
  let entityMap = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
    '/': '&#x2F;',
    '`': '&#x60;',
    '=': '&#x3D;'
  };

  return String(string).replace(/[&<>"'`=\/]/g, function (s) {
    return entityMap[s];
  });
}
