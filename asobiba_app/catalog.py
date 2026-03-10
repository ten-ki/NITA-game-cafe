GAMES = [
    {
        "id": "othello",
        "name": "オセロ",
        "players": "2人",
        "description": "石をひっくり返して勝負する定番ボードゲーム。",
    },
    {
        "id": "shogi",
        "name": "将棋",
        "players": "2人",
        "description": "持ち駒も使える本格将棋。合法手はサーバーで管理します。",
    },
    {
        "id": "uno",
        "name": "UNO",
        "players": "2〜4人",
        "description": "色と数字をつないで上がりを目指すカードゲーム。",
    },
    {
        "id": "gomoku",
        "name": "五目並べ",
        "players": "2人",
        "description": "5つ先に並べたら勝ちのシンプルな読み合い。",
    },
    {
        "id": "connect-four",
        "name": "四目並べ",
        "players": "2人",
        "description": "縦横斜めに4つそろえる落下型ボードゲーム。",
    },
    {
        "id": "daifugo",
        "name": "大富豪",
        "players": "2〜4人",
        "description": "同じ数字を出し合うシンプルルール版の大富豪。",
    },
]

GAME_MAP = {game["id"]: game for game in GAMES}
