const config = window.roomConfig;
const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/rooms/${config.roomCode}?token=${encodeURIComponent(config.wsToken)}`);

const gameRoot = document.getElementById("gameRoot");
const playersList = document.getElementById("playersList");
const spectatorList = document.getElementById("spectatorList");
const statusMessage = document.getElementById("statusMessage");
const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");

let latestState = null;
let shogiSelection = null;
let daifugoSelection = new Set();

const shogiLabels = {
  P: "歩", L: "香", N: "桂", S: "銀", G: "金", B: "角", R: "飛", K: "玉",
  "+P": "と", "+L": "成香", "+N": "成桂", "+S": "成銀", "+B": "馬", "+R": "龍"
};

socket.addEventListener("message", (event) => {
  latestState = JSON.parse(event.data);
  renderState(latestState);
});

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  socket.send(JSON.stringify({ type: "chat", text }));
  chatInput.value = "";
});

function sendAction(payload) {
  socket.send(JSON.stringify({ type: "action", payload }));
}

function renderState(state) {
  playersList.innerHTML = state.players.map((player) => `<li>${player.username} ${player.online ? "●" : "○"}</li>`).join("");
  spectatorList.innerHTML = state.spectators.length
    ? state.spectators.map((player) => `<li>${player.username}</li>`).join("")
    : "<li>なし</li>";
  statusMessage.textContent = `${state.status_message}${state.winner ? ` / ${state.winner}` : ""}`;
  chatLog.innerHTML = state.chat.length
    ? state.chat.map((entry) => `<div class="chat-line"><strong>${escapeHtml(entry.author)}</strong><div>${escapeHtml(entry.text)}</div></div>`).join("")
    : "<div class='muted'>まだチャットはありません。</div>";

  if (state.kind === "board-grid") renderBoardGrid(state);
  if (state.kind === "connect-four") renderConnectFour(state);
  if (state.kind === "shogi") renderShogi(state);
  if (state.kind === "uno") renderUno(state);
  if (state.kind === "daifugo") renderDaifugo(state);
}

function renderBoardGrid(state) {
  const validSet = new Set((state.valid_moves || []).map((move) => `${move.row}:${move.col}`));
  const boardClass = state.rows === 15 ? "board-15" : state.rows === 9 ? "board-9" : "board-8";
  gameRoot.innerHTML = `
    <div class="info-card">
      <strong>${state.title}</strong>
      <div class="muted">あなたの石: ${formatPiece(state.piece)}</div>
      ${state.scores ? `<div class="muted">黒 ${state.scores.B} / 白 ${state.scores.W}</div>` : ""}
    </div>
    <div class="board-grid ${boardClass}">
      ${state.board.map((row, rowIndex) => row.map((cell, colIndex) => {
        const key = `${rowIndex}:${colIndex}`;
        const valid = validSet.has(key);
        const content = cell === "." ? "" : `<div class="stone ${cell === "B" ? "black" : "white"}"></div>`;
        return `<button class="board-cell ${cell === "." ? "empty" : ""} ${valid ? "valid" : ""}" data-row="${rowIndex}" data-col="${colIndex}" ${valid ? "" : "disabled"}>${content}</button>`;
      }).join("")).join("")}
    </div>
  `;
  gameRoot.querySelectorAll(".board-cell").forEach((button) => {
    button.addEventListener("click", () => sendAction({ type: "place", row: button.dataset.row, col: button.dataset.col }));
  });
}

function renderConnectFour(state) {
  const validCols = new Set((state.valid_columns || []).map((item) => String(item.col)));
  gameRoot.innerHTML = `
    <div class="info-card">
      <strong>${state.title}</strong>
      <div class="muted">あなたの色: ${state.piece === "R" ? "赤" : state.piece === "Y" ? "黄" : "観戦"}</div>
    </div>
    <div class="column-row">
      ${Array.from({ length: state.cols }).map((_, col) => `<button class="column-button" data-col="${col}" ${validCols.has(String(col)) ? "" : "disabled"}>↓</button>`).join("")}
    </div>
    <div class="connect-board">
      ${state.board.map((row) => `<div class="connect-row">${row.map((cell) => `<div class="connect-slot">${cell === "." ? "" : `<div class="connect-piece ${cell === "R" ? "red" : "yellow"}"></div>`}</div>`).join("")}</div>`).join("")}
    </div>
  `;
  gameRoot.querySelectorAll(".column-button").forEach((button) => {
    button.addEventListener("click", () => sendAction({ type: "drop", col: button.dataset.col }));
  });
}

function renderShogi(state) {
  const yourHandKey = state.your_color === "black" ? "black" : state.your_color === "white" ? "white" : null;
  const boardHtml = state.board.map((row, rowIndex) => row.map((cell, colIndex) => {
    const square = squareName(rowIndex, colIndex);
    const piece = renderShogiPiece(cell);
    return `<button class="board-cell" data-square="${square}">${piece}</button>`;
  }).join("")).join("");

  gameRoot.innerHTML = `
    <div class="shogi-layout">
      <div class="shogi-hands">
        <div class="shogi-hand-box">
          <strong>先手の持ち駒</strong>
          <div class="shogi-hand-pieces">
            ${(state.hands.black || []).map((piece) => yourHandKey === "black"
              ? `<button class="hand-select" data-drop="${piece.code}">${piece.label} × ${piece.count}</button>`
              : `<span class="hand-select">${piece.label} × ${piece.count}</span>`).join("") || "<span class='muted'>なし</span>"}
          </div>
        </div>
        <div class="shogi-hand-box">
          <strong>後手の持ち駒</strong>
          <div class="shogi-hand-pieces">
            ${(state.hands.white || []).map((piece) => yourHandKey === "white"
              ? `<button class="hand-select" data-drop="${piece.code}">${piece.label} × ${piece.count}</button>`
              : `<span class="hand-select">${piece.label} × ${piece.count}</span>`).join("") || "<span class='muted'>なし</span>"}
          </div>
        </div>
      </div>
      <div class="info-card">
        <div>あなたの側: ${state.your_color === "black" ? "先手" : state.your_color === "white" ? "後手" : "観戦"}</div>
        <div class="muted">選択中: ${shogiSelection ? escapeHtml(JSON.stringify(shogiSelection)) : "なし"}</div>
      </div>
      <div class="board-grid board-9">${boardHtml}</div>
      <div class="shogi-controls">
        <button class="secondary-button" id="clearShogiSelect">選択をクリア</button>
        ${state.is_player && !state.winner ? `<button class="ghost-button" id="resignBtn">投了</button>` : ""}
      </div>
    </div>
  `;

  gameRoot.querySelectorAll("[data-drop]").forEach((button) => {
    button.addEventListener("click", () => {
      shogiSelection = { drop: button.dataset.drop };
      renderShogi(state);
    });
  });

  gameRoot.querySelectorAll("[data-square]").forEach((button) => {
    button.addEventListener("click", () => handleShogiSquare(state, button.dataset.square));
  });

  document.getElementById("clearShogiSelect")?.addEventListener("click", () => {
    shogiSelection = null;
    renderShogi(state);
  });

  document.getElementById("resignBtn")?.addEventListener("click", () => {
    if (confirm("投了しますか？")) sendAction({ type: "resign" });
  });
}

function handleShogiSquare(state, square) {
  const legalMoves = state.legal_moves || [];
  if (!shogiSelection) {
    const movesFrom = legalMoves.filter((move) => move.from === square);
    if (movesFrom.length) {
      shogiSelection = { from: square };
      renderShogi(state);
    }
    return;
  }
  const candidates = legalMoves.filter((move) => {
    if (shogiSelection.from) return move.from === shogiSelection.from && move.to === square;
    return move.drop === shogiSelection.drop && move.to === square;
  });
  if (!candidates.length) {
    shogiSelection = null;
    renderShogi(state);
    return;
  }
  let move = candidates[0];
  if (candidates.length === 2) {
    const promote = confirm("成りますか？");
    move = candidates.find((item) => item.promotion === promote) || candidates[0];
  }
  sendAction({ type: "move", usi: move.usi });
  shogiSelection = null;
}

function renderUno(state) {
  const top = state.top_card ? `<strong>場札:</strong> ${escapeHtml(state.top_card.label)} / 色: ${escapeHtml(state.current_color)}` : "待機中";
  gameRoot.innerHTML = `
    <div class="card-layout">
      <div class="info-card">
        <div>${top}</div>
        <div class="muted">あなたの番: ${state.turn_user_id == config.currentUserId}</div>
      </div>
      <div class="info-card">
        <strong>相手の手札枚数</strong>
        <div>${state.other_hands.map((item) => `${escapeHtml(item.username)}: ${item.count} 枚`).join("<br>") || "なし"}</div>
      </div>
      <div class="card-hand">
        ${state.your_hand.map((card) => `<button class="card-button" data-card="${card.id}" data-color="${card.color}">${escapeHtml(card.label)}</button>`).join("")}
      </div>
      <div class="color-picker">
        ${["red", "yellow", "green", "blue"].map((color) => `<button class="color-dot ${color}" data-pick-color="${color}" title="${color}"></button>`).join("")}
      </div>
      <div class="shogi-controls">
        <button class="action-button" id="drawUnoBtn">1枚引く</button>
      </div>
    </div>
  `;
  let selectedWildColor = "red";
  gameRoot.querySelectorAll("[data-pick-color]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedWildColor = button.dataset.pickColor;
    });
  });
  gameRoot.querySelectorAll("[data-card]").forEach((button) => {
    button.addEventListener("click", () => {
      sendAction({
        type: "play",
        card_id: button.dataset.card,
        chosen_color: button.dataset.color === "wild" ? selectedWildColor : undefined
      });
    });
  });
  document.getElementById("drawUnoBtn")?.addEventListener("click", () => sendAction({ type: "draw" }));
}

function renderDaifugo(state) {
  gameRoot.innerHTML = `
    <div class="card-layout">
      <div class="info-card">
        <div><strong>場</strong>: ${state.active_play ? `${escapeHtml(state.active_play.by)} / ${state.active_play.cards.join(", ")}` : "空です"}</div>
        <div class="muted">あなたの番: ${state.turn_user_id == config.currentUserId}</div>
      </div>
      <div class="info-card">
        <strong>相手の手札枚数</strong>
        <div>${state.other_hands.map((item) => `${escapeHtml(item.username)}: ${item.count} 枚`).join("<br>") || "なし"}</div>
      </div>
      <div class="card-hand">
        ${state.your_hand.map((card) => `<button class="card-button ${daifugoSelection.has(card.id) ? "selected" : ""}" data-daifugo-card="${card.id}">${escapeHtml(card.label)}</button>`).join("")}
      </div>
      <div class="shogi-controls">
        <button class="action-button" id="playDaifugoBtn">選択したカードを出す</button>
        <button class="secondary-button" id="passDaifugoBtn">パス</button>
      </div>
    </div>
  `;
  gameRoot.querySelectorAll("[data-daifugo-card]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.daifugoCard;
      if (daifugoSelection.has(id)) daifugoSelection.delete(id);
      else daifugoSelection.add(id);
      renderDaifugo(state);
    });
  });
  document.getElementById("playDaifugoBtn")?.addEventListener("click", () => {
    sendAction({ type: "play", card_ids: Array.from(daifugoSelection) });
    daifugoSelection.clear();
  });
  document.getElementById("passDaifugoBtn")?.addEventListener("click", () => sendAction({ type: "pass" }));
}

function squareName(row, col) {
  return `${9 - col}${String.fromCharCode(97 + row)}`;
}

function renderShogiPiece(token) {
  if (token === ".") return "";
  const normalized = token.replace(/[a-z]/g, (match) => match.toUpperCase());
  const label = shogiLabels[normalized] || normalized;
  const white = /[a-z]/.test(token);
  return `<div class="shogi-piece ${white ? "piece-white" : ""}">${label}</div>`;
}

function formatPiece(piece) {
  if (piece === "B") return "黒";
  if (piece === "W") return "白";
  if (piece === "R") return "赤";
  if (piece === "Y") return "黄";
  return piece || "観戦";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
