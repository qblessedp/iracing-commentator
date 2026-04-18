"""Offline template-based commentary generator.

No API key needed. Generates broadcast lines by picking from curated phrase
pools per event type and language. Anti-repetition via per-tag deque.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Iterable


class _SafeDict(dict):
    """dict.format_map helper: missing keys become '?' instead of KeyError."""

    def __missing__(self, key: str) -> str:  # noqa: D401
        return "?"


def _flag_key(flag: str) -> str:
    f = (flag or "").lower().strip()
    if "green" in f:
        return "flag_green"
    if "yellow" in f or "caution" in f:
        return "flag_yellow"
    if "red" in f:
        return "flag_red"
    if "blue" in f:
        return "flag_blue"
    if "white" in f:
        return "flag_white"
    if "checker" in f:
        return "flag_checkered"
    return "flag_generic"


# =====================================================================
# TEMPLATES: [lang][event_key] = list[str]
# Placeholders map to event_detector fields.
# =====================================================================
TEMPLATES: dict[str, dict[str, list[str]]] = {
    # ---------------------------------------------------------------
    # ENGLISH  (British F1 broadcast)
    # ---------------------------------------------------------------
    "en": {
        "overtake": [
            "{driver} makes the move, up into P{to_pos}!",
            "And there it is! {driver} muscles past for P{to_pos}.",
            "Beautiful overtake by {driver}, now P{to_pos}.",
            "{driver} with a brave move into P{to_pos}.",
            "Down the inside, {driver} takes P{to_pos}!",
            "{driver} gets the job done, up to P{to_pos} from P{from_pos}.",
            "Clinical from {driver}, slicing into P{to_pos}.",
            "That's a cracking overtake by {driver} for P{to_pos}!",
            "{driver} will not be denied — P{to_pos} is his.",
            "Into the braking zone, {driver} grabs P{to_pos}.",
            "A textbook pass by {driver}, now up to P{to_pos}.",
            "{driver} is on a charge, now P{to_pos}.",
            "What a move! {driver} into P{to_pos}.",
            "DRS does the trick for {driver}, P{to_pos} secured.",
            "{driver} gains a place, promoted to P{to_pos}.",
        ],
        "pit_entry": [
            "{driver} peels into the pit lane.",
            "{driver} is in for fresh rubber.",
            "Box, box — {driver} diving into the pits.",
            "{driver} commits to the stop.",
            "In comes {driver}, strategy playing out.",
            "{driver} abandons track position for a stop.",
            "The undercut is on — {driver} into the pits.",
            "{driver} rolls into the pit lane.",
            "Pit stop for {driver}, let's see the gain.",
            "{driver} takes the plunge into pit road.",
            "{driver} heads for the boxes.",
            "Strategy call — {driver} pitting now.",
        ],
        "pit_exit": [
            "{driver} back out on track, fresh tyres.",
            "And {driver} rejoins, let's see where he slots in.",
            "{driver} releases from the pits, boots on.",
            "Clean stop — {driver} is back in the fight.",
            "{driver} out of the pit lane, full beans now.",
            "Fresh rubber for {driver}, game on.",
            "{driver} rejoins the action.",
            "{driver} fires out of the pits.",
            "Stop completed — {driver} back on track.",
            "{driver} out, now on the charge.",
        ],
        "fastest_lap": [
            "Purple sector all the way — {driver} sets the fastest lap at {time}!",
            "{driver} lights up the timing screens with a {time}!",
            "Fastest lap of the session goes to {driver}, {time}.",
            "{driver} finds time where nobody else can — {time}.",
            "A stunning lap from {driver}, {time} and counting.",
            "That's a {time} — the benchmark belongs to {driver}.",
            "{driver} on the edge, {time} is the new fastest lap.",
            "Clocking a {time}, {driver} goes top of the pile.",
            "Purple, purple, purple — {driver} at {time}.",
            "{driver} throws down the gauntlet with a {time}.",
        ],
        "lead_change": [
            "We have a new leader! {new_driver} takes it from {old_driver}!",
            "{new_driver} is through — the race lead changes hands.",
            "Into the lead — {new_driver} deposes {old_driver}.",
            "{new_driver} snatches the lead from {old_driver}!",
            "The order at the front has flipped: {new_driver} leads.",
            "{old_driver} loses the lead, {new_driver} is now P1.",
            "Changing of the guard — {new_driver} heads the race.",
            "{new_driver} up to the front, {old_driver} swallowed up.",
            "A new name at the top: {new_driver} leads.",
            "{new_driver} finally finds a way past {old_driver}!",
        ],
        "flag_green": [
            "Green flag — we are go racing!",
            "Track is clear, green flag flying.",
            "Back to green — racing resumes.",
            "All clear, green lights all round.",
            "Green flag conditions, race back on.",
            "We're racing again, green flag.",
        ],
        "flag_yellow": [
            "Yellow flag on circuit — caution, caution.",
            "Yellows are out — drivers take note.",
            "Double waved yellow, something's happened.",
            "Yellow flag sector — ease off, drivers.",
            "Caution period — yellow flags waving.",
            "Yellow out on track, be careful out there.",
        ],
        "flag_red": [
            "Red flag! Session is stopped!",
            "Red flag — the session has come to a halt.",
            "We are red flagged. Drivers back to pit lane.",
            "Red flag out, something serious has happened.",
            "All cars pit, we are under a red flag.",
        ],
        "flag_blue": [
            "Blue flags waving — lapped traffic, be ready to move.",
            "Blue flag — let the leaders through.",
            "Traffic ahead, blue flags out.",
            "Blue flag for the backmarker.",
        ],
        "flag_white": [
            "White flag — slow car on the track.",
            "White flag out — caution for a slower car.",
            "Slow moving car ahead, white flag.",
        ],
        "flag_checkered": [
            "The checkered flag flies!",
            "Chequered flag — we are done!",
            "And the chequered flag comes out!",
        ],
        "flag_generic": [
            "Flag change on circuit: {flag}.",
            "We have a {flag} flag out on track.",
            "{flag} flag — pay attention, drivers.",
        ],
        "race_start": [
            "Lights out and away we go!",
            "It's lights out — the race is on!",
            "And they're racing! Clean getaway.",
            "Go, go, go — the race has begun!",
            "Five red lights out, we have a race on our hands!",
            "Off they go into turn one!",
            "The race is underway!",
        ],
        "battle": [
            "Wheel to wheel for P{position} — {leader_driver} defending from {chaser_driver}, just {gap} seconds.",
            "A proper scrap for P{position}: {chaser_driver} all over the back of {leader_driver}.",
            "{chaser_driver} is right there, {gap} seconds behind {leader_driver} for P{position}.",
            "Pressure building on {leader_driver}, {chaser_driver} sniffing P{position}.",
            "Just {gap} seconds separate {leader_driver} and {chaser_driver} in the fight for P{position}.",
            "The gap to {leader_driver} tumbles — {chaser_driver} {gap} seconds back.",
            "Big battle for P{position} between {leader_driver} and {chaser_driver}.",
            "{chaser_driver} in DRS range of {leader_driver} for P{position}.",
            "A fascinating duel for P{position} unfolding in front of us.",
            "{leader_driver} under real threat from {chaser_driver}, {gap} seconds the gap.",
        ],
        "accident_suspected": [
            "{driver} appears to be stopped on track — trouble for him.",
            "{driver} has come to a halt, that does not look good.",
            "Something wrong for {driver}, stopped on the circuit.",
            "{driver} is stationary out there, possible mechanical.",
            "Big problem for {driver} — he's parked it.",
            "{driver} off the racing line and stopped.",
            "Accident! {driver} is in the barriers!",
            "Oh no — {driver} has crashed out!",
            "{driver} loses it and buries it in the gravel.",
            "That's a heavy shunt for {driver}!",
            "Contact! {driver} is out of the race.",
            "{driver} has lost control — into the wall.",
            "Massive moment for {driver}, he's off!",
            "{driver} spins and parks it in the run-off.",
            "Disaster for {driver} — race over.",
            "That is a proper accident — {driver} hard into the barriers.",
            "{driver}'s race ends in the gravel trap.",
            "Heartbreak for {driver}, stopped and smoking.",
            "Huge hit for {driver}! The car is destroyed.",
            "{driver} goes straight on at the chicane — beached!",
            "End of the road for {driver}, nosed into the tyre wall.",
        ],
        "laps_to_go": [
            "{laps} laps to go — here comes the crunch.",
            "Into the final stages — {laps} laps remaining.",
            "{laps} laps left — strategy versus pace now.",
            "We're down to {laps} laps.",
            "{laps} to run — time is running out.",
            "The board shows {laps} to go.",
            "{laps} laps remain in this one.",
        ],
        "checkered": [
            "Across the line — the chequered flag falls!",
            "Race over — the chequered flag is out!",
            "The chequered flag waves — what a race!",
            "They take the flag!",
        ],
    },
    # ---------------------------------------------------------------
    # PORTUGUESE (PT-PT, F1 vocab)
    # ---------------------------------------------------------------
    "pt": {
        "overtake": [
            "{driver} ataca e sobe para P{to_pos}!",
            "Ultrapassagem de {driver}, agora em P{to_pos}.",
            "Bela manobra de {driver}, P{to_pos} e dele.",
            "{driver} nao perdoou, P{to_pos} conquistado.",
            "Por dentro, {driver} passa para P{to_pos}.",
            "Trabalho feito por {driver}, de P{from_pos} para P{to_pos}.",
            "{driver} sobe ao ataque, agora P{to_pos}.",
            "Que ultrapassagem de {driver}, P{to_pos}!",
            "{driver} nao se fez rogado, P{to_pos}.",
            "Travagem forte e {driver} segura P{to_pos}.",
            "Manobra de manual de {driver}, P{to_pos} e seu.",
            "{driver} em grande forma, agora P{to_pos}.",
            "DRS a fazer efeito, {driver} em P{to_pos}.",
            "{driver} ganha uma posicao, P{to_pos}.",
            "Golpe certeiro de {driver}, P{to_pos}.",
        ],
        "pit_entry": [
            "{driver} entra nas boxes.",
            "Paragem para {driver}, pneus frescos a caminho.",
            "{driver} ruma a pit lane.",
            "Vamos ver a estrategia — {driver} nas boxes.",
            "{driver} abandona a pista pela pit lane.",
            "Box, box para {driver}.",
            "A jogada do undercut em {driver}.",
            "{driver} mete-se na pit lane.",
            "Paragem nas boxes para {driver}.",
            "{driver} desvia para a pit lane.",
        ],
        "pit_exit": [
            "{driver} de volta a pista com borracha nova.",
            "E {driver} reentra, vamos ver onde se insere.",
            "Paragem limpa — {driver} de volta ao ataque.",
            "{driver} sai das boxes com tudo.",
            "Pneus novos e {driver} de volta.",
            "{driver} sai da pit lane.",
            "{driver} regressa ao combate.",
            "E {driver} esta de volta, a todo o gas.",
            "Saida rapida e {driver} esta na pista.",
        ],
        "fastest_lap": [
            "Volta mais rapida para {driver} com {time}!",
            "{driver} marca {time}, volta mais rapida!",
            "Que volta de {driver}! {time}!",
            "Sector roxo em todo o lado — {driver} com {time}.",
            "{driver} passa para o topo dos tempos com {time}.",
            "Novo recorde de volta: {driver} em {time}.",
            "{driver} no limite, {time} e o tempo de referencia.",
            "Cronometro a arder: {driver} com {time}.",
        ],
        "lead_change": [
            "Nova lideranca! {new_driver} passa {old_driver}!",
            "{new_driver} destrona {old_driver} e assume a lideranca.",
            "Troca de lideres — {new_driver} a frente.",
            "{new_driver} toma conta da corrida!",
            "Ja nao e {old_driver} — {new_driver} lidera.",
            "{new_driver} chega a frente, {old_driver} recua.",
            "Nova cara na lideranca: {new_driver}.",
            "{new_driver} finalmente apanha {old_driver} e passa-o.",
        ],
        "flag_green": [
            "Bandeira verde — pista livre!",
            "Verde outra vez, corrida normalizada.",
            "Verde — corrida de volta ao normal.",
            "Regresso ao verde, a corrida continua.",
        ],
        "flag_yellow": [
            "Bandeira amarela — atencao no sector.",
            "Amarela desfraldada, pilotos com cuidado.",
            "Dupla amarela — algo aconteceu.",
            "Regime de amarelas.",
            "Amarela no sector — aliviar a carga.",
        ],
        "flag_red": [
            "Bandeira vermelha! Sessao interrompida.",
            "Vermelha a acenar — corrida parada.",
            "Tudo parado, bandeira vermelha.",
            "Regresso as boxes — bandeira vermelha.",
        ],
        "flag_blue": [
            "Bandeiras azuis — retardatarios, deem passagem.",
            "Azul — deixar passar os lideres.",
            "Trafego a frente, azul a acenar.",
        ],
        "flag_white": [
            "Bandeira branca — carro lento na pista.",
            "Branca a acenar, cuidado com o carro lento.",
        ],
        "flag_checkered": [
            "Bandeira de xadrez!",
            "Xadrezada a cair!",
            "E cai a xadrezada!",
        ],
        "flag_generic": [
            "Mudanca de bandeira: {flag}.",
            "Bandeira {flag} em pista.",
            "Atentos a bandeira {flag}.",
        ],
        "race_start": [
            "Apagam-se as luzes e la vao eles!",
            "Luzes apagadas — corrida comecada!",
            "E comeca a corrida!",
            "Arrancada limpa, esta tudo a andar!",
            "Os semaforos apagam-se — vamos a corrida!",
            "Partida dada!",
        ],
        "battle": [
            "Roda com roda em P{position} — {leader_driver} a defender de {chaser_driver}, apenas {gap} segundos.",
            "Luta renhida por P{position}: {chaser_driver} colado a {leader_driver}.",
            "{chaser_driver} esta ali, a {gap} segundos de {leader_driver} em P{position}.",
            "Pressao em cima de {leader_driver}, {chaser_driver} a cheirar P{position}.",
            "So {gap} segundos entre {leader_driver} e {chaser_driver} em P{position}.",
            "Duelo interessante por P{position} entre {leader_driver} e {chaser_driver}.",
            "{chaser_driver} no DRS de {leader_driver} a lutar por P{position}.",
            "{leader_driver} sob ameaca de {chaser_driver}, {gap} segundos de diferenca.",
        ],
        "accident_suspected": [
            "{driver} parece estar parado em pista — problema para ele.",
            "{driver} imobilizado, nao parece nada bom.",
            "Algo de errado com {driver}, parado no circuito.",
            "{driver} esta parado, possivel problema mecanico.",
            "Problemao para {driver} — carro parado.",
            "Acidente! {driver} contra as barreiras!",
            "Oh nao — {driver} despistou-se!",
            "{driver} perde o controlo e vai para a gravilha.",
            "Grande pancada de {driver}!",
            "Choque! {driver} esta fora da corrida.",
            "{driver} bate no muro, corrida terminada.",
            "Momento enorme para {driver}, sai de pista!",
            "{driver} roda e fica atolado no escape.",
            "Desastre para {driver} — fim de corrida.",
            "Acidente a serio — {driver} forte contra o rail.",
            "{driver} termina a corrida no caixote da gravilha.",
            "Desgosto para {driver}, parado e a fumegar.",
            "Pancada brutal de {driver}! O carro ficou destruido.",
            "{driver} segue em frente na chicane — encravado!",
            "Fim de linha para {driver}, de nariz contra os pneus.",
        ],
        "laps_to_go": [
            "Faltam {laps} voltas — chega a hora da verdade.",
            "Entramos na reta final — {laps} voltas.",
            "{laps} voltas a espera, pressao ao maximo.",
            "Restam {laps} voltas.",
            "{laps} voltas ate a meta.",
            "O quadro mostra {laps} voltas.",
        ],
        "checkered": [
            "Cruza a meta — cai a xadrezada!",
            "Fim de corrida — xadrezada!",
            "Xadrezada — que corrida!",
            "E cai a bandeira!",
        ],
    },
    # ---------------------------------------------------------------
    # SPANISH  (peninsular, F1)
    # ---------------------------------------------------------------
    "es": {
        "overtake": [
            "{driver} ataca y sube a P{to_pos}!",
            "Adelantamiento de {driver}, ahora P{to_pos}.",
            "Gran maniobra de {driver}, P{to_pos} para el.",
            "{driver} no perdona, se queda con P{to_pos}.",
            "Por dentro, {driver} se lleva P{to_pos}.",
            "Trabajo hecho por {driver}: de P{from_pos} a P{to_pos}.",
            "{driver} sube al ataque, ahora P{to_pos}.",
            "Que adelantamiento de {driver}! P{to_pos}.",
            "{driver} no se lo piensa, P{to_pos} es suyo.",
            "Frenada fuerte y {driver} se queda con P{to_pos}.",
            "Adelantamiento de manual de {driver}, P{to_pos}.",
            "{driver} en racha, ahora P{to_pos}.",
            "DRS haciendo efecto, {driver} en P{to_pos}.",
            "{driver} gana una plaza, P{to_pos}.",
        ],
        "pit_entry": [
            "{driver} entra a boxes.",
            "Parada para {driver}, gomas frescas.",
            "{driver} enfila la calle de boxes.",
            "Veamos la estrategia — {driver} a boxes.",
            "{driver} abandona pista rumbo a boxes.",
            "Box, box para {driver}.",
            "Jugada del undercut para {driver}.",
            "{driver} hacia la pit lane.",
            "{driver} se desvia a boxes.",
        ],
        "pit_exit": [
            "{driver} de vuelta a pista con gomas nuevas.",
            "Y {driver} reincorporado, veamos su posicion.",
            "Parada limpia — {driver} de regreso.",
            "{driver} sale de boxes a tope.",
            "Neumaticos nuevos y {driver} vuelve.",
            "{driver} abandona pit lane.",
            "{driver} regresa a la batalla.",
            "{driver} esta de vuelta, a por todas.",
        ],
        "fastest_lap": [
            "Vuelta rapida para {driver} con {time}!",
            "{driver} firma un {time}, vuelta rapida!",
            "Que vuelta de {driver}! {time}!",
            "Sectores morados — {driver} en {time}.",
            "{driver} manda en los tiempos con {time}.",
            "Nuevo mejor giro: {driver} en {time}.",
            "{driver} al limite, {time} de referencia.",
            "Cronos ardiendo — {driver} en {time}.",
        ],
        "lead_change": [
            "Nuevo lider! {new_driver} supera a {old_driver}!",
            "{new_driver} destrona a {old_driver}.",
            "Cambio al frente — {new_driver} en cabeza.",
            "{new_driver} toma el mando de la carrera!",
            "Ya no es {old_driver} — {new_driver} lidera.",
            "{new_driver} al frente, {old_driver} cae.",
            "Nueva cara en cabeza: {new_driver}.",
            "{new_driver} por fin pasa a {old_driver}!",
        ],
        "flag_green": [
            "Bandera verde — pista libre!",
            "Verde de nuevo, carrera normalizada.",
            "Verde — seguimos en carrera.",
            "Vuelta al verde.",
        ],
        "flag_yellow": [
            "Bandera amarilla — precaucion en el sector.",
            "Amarillas al aire, cuidado pilotos.",
            "Doble amarilla — algo ha pasado.",
            "Regimen de amarillas.",
            "Amarilla en sector — levantar el pie.",
        ],
        "flag_red": [
            "Bandera roja! Sesion detenida.",
            "Roja al viento — carrera parada.",
            "Todo parado, bandera roja.",
            "De vuelta a boxes — bandera roja.",
        ],
        "flag_blue": [
            "Azules — retrasados, dejad pasar.",
            "Azul — dar paso a los lideres.",
            "Trafico delante, azul.",
        ],
        "flag_white": [
            "Bandera blanca — coche lento en pista.",
            "Blanca al aire, cuidado con el lento.",
        ],
        "flag_checkered": [
            "Bandera a cuadros!",
            "Cuadros al viento!",
            "Y cae la bandera a cuadros!",
        ],
        "flag_generic": [
            "Cambio de bandera: {flag}.",
            "Bandera {flag} en pista.",
            "Atentos a la {flag}.",
        ],
        "race_start": [
            "Se apagan las luces y alla van!",
            "Luces fuera — arranca la carrera!",
            "Y comienza la carrera!",
            "Salida limpia, todos en marcha!",
            "Se apagan los semaforos — vamos!",
            "Carrera en marcha!",
        ],
        "battle": [
            "Rueda con rueda por P{position} — {leader_driver} defendiendo de {chaser_driver}, solo {gap} segundos.",
            "Batalla por P{position}: {chaser_driver} pegado a {leader_driver}.",
            "{chaser_driver} ahi mismo, a {gap} segundos de {leader_driver} por P{position}.",
            "Presion para {leader_driver}, {chaser_driver} olfatea P{position}.",
            "Solo {gap} segundos entre {leader_driver} y {chaser_driver} por P{position}.",
            "Duelo apasionante por P{position}.",
            "{chaser_driver} en DRS de {leader_driver}.",
            "{leader_driver} bajo amenaza de {chaser_driver}, {gap} segundos.",
        ],
        "accident_suspected": [
            "{driver} parece detenido en pista — problemas.",
            "{driver} parado, mala pinta.",
            "Algo falla en {driver}, inmovil en el circuito.",
            "{driver} se queda clavado, posible mecanica.",
            "Problema serio para {driver}.",
            "Accidente! {driver} contra las barreras!",
            "Oh no — {driver} se ha estrellado!",
            "{driver} pierde el control y acaba en la grava.",
            "Gran golpe para {driver}!",
            "Contacto! {driver} fuera de carrera.",
            "{driver} contra el muro, carrera terminada.",
            "Momento enorme para {driver}, se sale!",
            "{driver} trompea y se queda atrapado en el escape.",
            "Desastre para {driver} — fin de carrera.",
            "Accidente serio — {driver} con fuerza contra el rail.",
            "Final de carrera para {driver} en la trampa de grava.",
            "Mala suerte para {driver}, parado y humeando.",
            "Golpe brutal de {driver}! El coche ha quedado destrozado.",
            "{driver} sigue recto en la chicane — atascado!",
            "Se acabo para {driver}, de morro contra los neumaticos.",
        ],
        "laps_to_go": [
            "Quedan {laps} vueltas — llega la hora de la verdad.",
            "Recta final — {laps} vueltas.",
            "{laps} vueltas por delante, presion al maximo.",
            "Restan {laps} vueltas.",
            "{laps} vueltas hasta la meta.",
            "El panel marca {laps} vueltas.",
        ],
        "checkered": [
            "Cruza la meta — bandera a cuadros!",
            "Final de carrera — cuadros!",
            "Cuadros — que carrera!",
            "Y cae la bandera final!",
        ],
    },
    # ---------------------------------------------------------------
    # JAPANESE  (F1 broadcast style)
    # ---------------------------------------------------------------
    "jp": {
        "overtake": [
            "{driver}、オーバーテイクでP{to_pos}！",
            "見事な仕掛け！{driver}がP{to_pos}。",
            "{driver}、前を捉えてP{to_pos}。",
            "果敢に{driver}がP{to_pos}を奪う。",
            "インから{driver}、P{to_pos}。",
            "{driver}、P{from_pos}からP{to_pos}へ。",
            "{driver}の一発、P{to_pos}獲得！",
            "DRSで{driver}、P{to_pos}へ。",
            "{driver}が順位を上げてP{to_pos}。",
            "鋭いブレーキング、{driver}がP{to_pos}。",
            "{driver}、綺麗なパスでP{to_pos}。",
        ],
        "pit_entry": [
            "{driver}、ピットイン。",
            "{driver}、ピットレーンへ。",
            "ボックス、ボックス — {driver}。",
            "{driver}、タイヤ交換に入ります。",
            "戦略の一手、{driver}がピットへ。",
            "アンダーカット狙い、{driver}がピットイン。",
            "{driver}、ピットに飛び込む。",
        ],
        "pit_exit": [
            "{driver}、ピットアウト。",
            "{driver}、コースに復帰。",
            "新しいタイヤで{driver}がコースへ。",
            "クリーンなストップ、{driver}復帰。",
            "{driver}、ピットレーンを後に。",
            "{driver}、再びバトルへ。",
        ],
        "fastest_lap": [
            "ファステストラップ！{driver}が{time}！",
            "{driver}、{time}で最速タイム！",
            "パープルセクター連発、{driver}が{time}。",
            "{driver}、タイムシートのトップへ、{time}。",
            "新たな基準タイム：{driver}、{time}。",
            "{driver}が限界に挑む、{time}。",
        ],
        "lead_change": [
            "トップ交代！{new_driver}が{old_driver}を抜いた！",
            "{new_driver}がリードを奪取！",
            "首位が入れ替わる — {new_driver}。",
            "{old_driver}に代わり{new_driver}がトップ。",
            "{new_driver}、ついに{old_driver}を攻略！",
            "レースの先頭は{new_driver}。",
        ],
        "flag_green": [
            "グリーンフラッグ — レース再開！",
            "クリア、グリーン。",
            "グリーンフラッグが振られています。",
        ],
        "flag_yellow": [
            "イエローフラッグ — 注意！",
            "イエロー提示、ドライバー注意。",
            "ダブルイエロー — 何かが起きた模様。",
            "セクターにイエロー。",
        ],
        "flag_red": [
            "赤旗！セッション中断。",
            "レッドフラッグ、全車ピットへ。",
            "赤旗提示、走行停止。",
        ],
        "flag_blue": [
            "ブルーフラッグ — 周回遅れは道を空けて。",
            "ブルー提示、先頭を通す。",
        ],
        "flag_white": [
            "白旗 — 低速車に注意。",
            "ホワイトフラッグ提示。",
        ],
        "flag_checkered": [
            "チェッカードフラッグ！",
            "チェッカーが振られる！",
        ],
        "flag_generic": [
            "フラッグ変化：{flag}。",
            "{flag}フラッグ提示。",
        ],
        "race_start": [
            "ライトアウト、レーススタート！",
            "シグナル消灯、スタート！",
            "レースが始まりました！",
            "5つのライトが消えた — スタート！",
            "クリーンなスタート！",
        ],
        "battle": [
            "P{position}争い — {leader_driver}と{chaser_driver}、差は{gap}秒。",
            "{chaser_driver}が{leader_driver}に接近、P{position}争い。",
            "わずか{gap}秒、P{position}をめぐる戦い。",
            "{leader_driver}にプレッシャー、{chaser_driver}が肉薄。",
            "P{position}の面白いバトル、{leader_driver} vs {chaser_driver}。",
            "{chaser_driver}、DRS圏内へ。",
        ],
        "accident_suspected": [
            "{driver}、コース上で停止 — トラブルか。",
            "{driver}が止まっている、マシントラブルの可能性。",
            "{driver}、マシンを止める。",
            "{driver}にアクシデントの気配。",
            "アクシデント！{driver}がバリアに！",
            "なんと — {driver}がクラッシュ！",
            "{driver}、コントロールを失いグラベルへ。",
            "{driver}に大きな衝撃！",
            "接触！{driver}、レースアウト。",
            "{driver}、ウォールに激突 — レース終了。",
            "大きな瞬間、{driver}がコースアウト！",
            "{driver}、スピンしてランオフに刺さる。",
            "{driver}にとって大惨事 — レース終了。",
            "本格的なアクシデント — {driver}がバリアに激突。",
            "{driver}のレースはグラベルトラップで終わる。",
            "{driver}、無念の停止、白煙を上げる。",
            "{driver}、大クラッシュ！マシンは大破。",
            "{driver}、シケインを直進 — スタック！",
            "{driver}、タイヤバリアに突っ込んで終了。",
        ],
        "laps_to_go": [
            "残り{laps}周 — 正念場。",
            "ファイナルラップへ — あと{laps}周。",
            "残り{laps}周、プレッシャー最高潮。",
            "あと{laps}周を残すのみ。",
            "{laps}周を切った。",
        ],
        "checkered": [
            "チェッカードフラッグ！",
            "ゴール — チェッカー！",
            "見事なレース、チェッカー！",
        ],
    },
}


def _event_key(event: dict) -> str:
    """Map an event dict to a template key."""
    t = (event.get("type") or "").lower()
    if t == "flag_change":
        return _flag_key(event.get("flag", ""))
    return t


class TemplateCommentator:
    """Offline commentary generator — no network, no API key."""

    def __init__(self, history_per_tag: int = 8) -> None:
        self._recent: dict[str, deque[str]] = {}
        self._history_per_tag = history_per_tag
        self._rng = random.Random()

    def _pool(self, language: str, key: str) -> list[str]:
        lang = (language or "en").lower()
        lang_pool = TEMPLATES.get(lang) or TEMPLATES["en"]
        return lang_pool.get(key) or lang_pool.get("flag_generic") or []

    def _pick(self, tag: str, options: Iterable[str]) -> str:
        opts = list(options)
        if not opts:
            return ""
        recent = self._recent.setdefault(tag, deque(maxlen=self._history_per_tag))
        pool = [o for o in opts if o not in recent] or opts
        choice = self._rng.choice(pool)
        recent.append(choice)
        return choice

    def generate(self, event: dict, language: str = "en") -> str:
        """Return a single broadcast-style line for the given event."""
        if not event:
            return ""
        key = _event_key(event)
        template = self._pick(f"{language}:{key}", self._pool(language, key))
        if not template:
            return ""
        try:
            return template.format_map(_SafeDict(event))
        except Exception:
            return template
