#!/usr/bin/env bash
# Sets photo, title, description of the channels and posts + pins a welcome post. Run on the server.
set -u
API=https://api.telegram.org
tok() { grep ^BOT_TOKEN= /opt/tenge/$1/.env | cut -d= -f2-; }
call() { curl -s "$API/bot$1/$2" "${@:3}" | python3 -c "import sys,json;d=json.load(sys.stdin);print('  ',('ok' if d['ok'] else 'FAIL '+str(d.get('description'))))"; }

setup() { # bot channel photo title description text button1label button1url [button2label button2url]
  local bot=$1 ch=$2 photo=$3 title=$4 desc=$5 text=$6; shift 6
  local T; T=$(tok "$bot")
  echo "== $ch"
  echo " photo";  call "$T" setChatPhoto --form-string chat_id="$ch" -F photo=@"$photo"
  echo " title";  call "$T" setChatTitle --data-urlencode chat_id="$ch" --data-urlencode title="$title"
  echo " about";  call "$T" setChatDescription --data-urlencode chat_id="$ch" --data-urlencode description="$desc"
  local kb; kb=$(python3 - "$@" <<'PY'
import json, sys
a = sys.argv[1:]
rows = [[{"text": a[i], "url": a[i + 1]}] for i in range(0, len(a), 2)]
print(json.dumps({"inline_keyboard": rows}))
PY
)
  local r; r=$(curl -s "$API/bot$T/sendMessage" --data-urlencode chat_id="$ch" --data-urlencode parse_mode=HTML \
      --data-urlencode text="$text" --data-urlencode reply_markup="$kb" --data-urlencode disable_web_page_preview=true)
  local mid; mid=$(echo "$r" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['result']['message_id'] if d['ok'] else '')")
  if [ -z "$mid" ]; then echo " post FAIL: $r"; return; fi
  echo " post ok ($mid)"
  echo " pin"; call "$T" pinChatMessage -d chat_id="$ch" -d message_id="$mid" -d disable_notification=true
}

B=/tmp/brand
setup geekdigest @geekdigests $B/geekdigests.jpg "Гик-дайджест" \
"Главное из мира ИИ, игр, техники и науки: один выпуск в день, 9:00 по Алматы. Со ссылками, без воды. Бот: @geekdigest_bot. English edition: @geekdigest_eng" \
$'👋 <b>Гик-дайджест</b>\n\nКаждое утро в 9:00 (Алматы): обложка и по 3 новости из рубрик 🤖 ИИ, 💻 Техника, 🎮 Игры, 🔬 Наука. Со ссылками на источники, без воды и кликбейта.\n\n🔔 Удобнее получать выпуск в личку? Жми кнопку ниже.\n\nЕщё от нас: @wordlores · @ideaforges' \
  "🔔 Получать в личку" "https://t.me/geekdigest_bot?start=sub" "🇬🇧 English edition" "https://t.me/geekdigest_eng"

setup geekdigest @geekdigest_eng $B/geekdigest_eng.jpg "Geek Digest" \
"The best of AI, games, tech and science: one issue a day, 9:00 Almaty time. Links included, no fluff. Bot: @geekdigest_bot. Русская версия: @geekdigests" \
$'👋 <b>Geek Digest</b>\n\nEvery morning at 9:00 (Almaty time): a cover and 3 stories each from 🤖 AI, 💻 Tech, 🎮 Games and 🔬 Science. Source links included, no fluff or clickbait.\n\n🔔 Prefer to get it in a chat? Tap the button below.\n\nMore from us: @wordlores · @ideaforges' \
  "🔔 Send it to my chat" "https://t.me/geekdigest_bot?start=sub" "🇷🇺 Русская версия" "https://t.me/geekdigests"

setup wordlore @wordlores $B/wordlores.jpg "Wordlore · истории слов" \
"Каждое утро в 10:00 (Алматы) одно слово и его настоящая история: откуда пришло и что значило раньше. Викторина, серии, ранги и дуэли с друзьями в боте @wordlore_bot" \
$'📖 <b>Wordlore: истории слов</b>\n\nПочему «робот» это «подневольный труд»? Что общего у «зарплаты» и соли? Каждое утро в 10:00 (Алматы) одно слово и цепочка, по которой оно дошло до нас.\n\n🧠 В боте: викторина из 5 вопросов, серии, ранги и дуэли с друзьями. Первый раунд каждый день бесплатно.\n\nЕщё от нас: @geekdigests · @ideaforges' \
  "🧠 Сыграть в викторину" "https://t.me/wordlore_bot?start=quiz" "🔔 Слово дня в личку" "https://t.me/wordlore_bot?start=sub"

setup ideaforgegen @ideaforges $B/ideaforges.jpg "IdeaForge · идеи для игр и НРИ" \
"Каждый вечер идея для игры, персонаж, фракция, артефакт, квест или локация. Хочешь свою? Бот @ideaforge_gen_bot: 5 карточек в день бесплатно, наборы для кампаний и PDF-колоды" \
$'🔥 <b>IdeaForge: кузница идей</b>\n\nКаждый вечер новая карточка: идея игры, персонаж с секретом, фракция, артефакт, квест или локация. Для разработчиков игр и мастеров настольных ролёвок.\n\n🎲 Нужна своя? В боте 5 карточек в день бесплатно, наборы для целой кампании и PDF-колода для печати.\n\nЕщё от нас: @geekdigests · @wordlores' \
  "🎲 Сгенерировать идею" "https://t.me/ideaforge_gen_bot" "🔔 Идея дня в личку" "https://t.me/ideaforge_gen_bot?start=sub"
