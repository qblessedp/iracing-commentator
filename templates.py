"""Offline template-based commentary generator.

No API key needed. Generates broadcast lines by picking from curated phrase
pools per session type / event type / language. Anti-repetition via per-tag
deque.

Pool resolution order for a given (language, session_type, event_key):
    TEMPLATES[lang][session_type][event_key]
 -> TEMPLATES[lang]["race"][event_key]
 -> TEMPLATES[lang]["race"]["flag_generic"]
 -> []

Phrasing style: broadcast-natural, contractions, interjections, incomplete
sentences, the occasional aside — the way a real commentator actually talks,
not how a press release reads.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Iterable

SESSION_KEYS = ("practice", "qualifying", "race")


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


def _session_key(session_type: str) -> str:
    s = (session_type or "").lower()
    if "qual" in s:
        return "qualifying"
    if "practice" in s or "warmup" in s or "test" in s:
        return "practice"
    return "race"


# =====================================================================
# TEMPLATES: [lang][session_type][event_key] = list[str]
# =====================================================================
TEMPLATES: dict[str, dict[str, dict[str, list[str]]]] = {
    # ---------------------------------------------------------------
    # ENGLISH  (British F1 broadcast)
    # ---------------------------------------------------------------
    "en": {
        "race": {
            "overtake": [
                "And there it is — {driver}, up into P{to_pos}!",
                "Oh, lovely move from {driver}, that's P{to_pos}.",
                "{driver} sends it down the inside — P{to_pos}, just like that.",
                "Hang on, {driver}'s done him! P{to_pos}.",
                "That's beautifully judged from {driver} — P{to_pos}.",
                "{driver} isn't hanging about, is he? Up to P{to_pos}.",
                "Brave, that — {driver} takes P{to_pos}.",
                "Into the braking zone and yes, {driver} has P{to_pos}.",
                "Look at this — {driver}, right up the inside, P{to_pos}.",
                "Done and dusted — {driver} moves into P{to_pos}.",
                "Well, that's a statement from {driver}. P{to_pos}.",
                "{driver} with the DRS, and he's through for P{to_pos}.",
                "From P{from_pos} to P{to_pos} — {driver} is on a charge.",
                "Oh, cheeky! {driver} nicks P{to_pos}.",
                "He's had him. {driver} — P{to_pos}.",
            ],
            "pit_entry": [
                "And {driver}'s peeling off into the pits.",
                "Right, here comes {driver} — box, box.",
                "{driver}'s had enough of those tyres — into the pit lane.",
                "In comes {driver}. Let's see what they go on to.",
                "{driver} diving for the pits — could be the undercut.",
                "That's the call — {driver} is stopping.",
                "Pit lane for {driver}, gambling on the window.",
                "Down the lane goes {driver}.",
                "Strategy time — {driver}'s in.",
                "{driver} surrenders track position. Big call.",
            ],
            "pit_exit": [
                "And {driver}'s back out, fresh boots on.",
                "Out he comes — {driver}, and it looked clean enough.",
                "{driver} rejoins. Now the question is, where?",
                "Tyres bolted on — {driver}'s away.",
                "Full beans from {driver} out of the pit lane.",
                "{driver} back in the fight, new rubber.",
                "Stop done, {driver} is on his way.",
                "Lovely work from the crew — {driver} fires out.",
                "Right, {driver}'s out. Let's see the undercut land.",
            ],
            "fastest_lap": [
                "Ooh, purple everywhere — {driver}, a {time}!",
                "Fastest lap of the race, {driver}, {time}. Lovely.",
                "{driver}'s lighting up the screens — {time}.",
                "That's the benchmark — {driver}, {time}.",
                "Well, where did that come from? {driver}, {time}.",
                "A {time} for {driver}. He's finding it everywhere.",
                "Purple, purple, purple — {driver}, {time}.",
                "Fastest of the race for {driver}. {time}.",
                "{driver}'s throwing the kitchen sink at it — {time}.",
                "Quick lap, that. {driver}, {time}.",
            ],
            "lead_change": [
                "And we have a new leader! {new_driver} is through on {old_driver}!",
                "He's done it — {new_driver} into the lead!",
                "There's the move for the win — {new_driver} heads the race.",
                "Goodbye {old_driver}, hello {new_driver} out front.",
                "{new_driver} has taken the lead from {old_driver}!",
                "Into P1 — {new_driver}. What a moment.",
                "The lead changes hands! {new_driver} ahead.",
                "That is huge — {new_driver} leads the race.",
            ],
            "flag_green": [
                "Green flag — and off we go again.",
                "Clear track, we're racing.",
                "Back to green. Elbows out, everyone.",
                "Green, green, green — race is on.",
                "All clear now, back up to speed.",
            ],
            "flag_yellow": [
                "Yellows — heads up, drivers.",
                "Double-waved yellows, something's happened.",
                "Careful now, yellow in the sector.",
                "Yellow flag out — ease it off.",
                "Caution period, yellows flying.",
            ],
            "flag_red": [
                "Red flag. The session is stopped.",
                "That's a red — back to the pit lane, everyone.",
                "Red flag. Something serious.",
                "All stop — red flag.",
                "We are red flagged. Drivers, pit lane.",
            ],
            "flag_blue": [
                "Blue flags — he needs to move over.",
                "Blues out, leaders coming through.",
                "Traffic — blue flag for the backmarker.",
                "Blue flag, let them by.",
            ],
            "flag_white": [
                "White flag — slow car ahead.",
                "Careful, white flag, someone's crawling.",
                "Slow-moving car — white flag's out.",
            ],
            "flag_checkered": [
                "And the chequered flag falls!",
                "There it is — the chequered flag!",
                "Across the line — chequered flag!",
            ],
            "flag_generic": [
                "Flag change on circuit — {flag}.",
                "{flag} flag out. Eyes up.",
                "Heads up, {flag} flag showing.",
            ],
            "race_start": [
                "Lights out, and away we go!",
                "It's lights out — they're racing!",
                "Go, go, go — the race is on!",
                "Five red lights — out — and we have a race!",
                "Off they go, into turn one.",
                "Clean getaway and the race is underway.",
            ],
            "battle": [
                "Wheel to wheel for P{position} — {leader_driver} holding off {chaser_driver}, {gap} seconds.",
                "Proper scrap, this — {chaser_driver} all over the back of {leader_driver}.",
                "Only {gap} seconds between {leader_driver} and {chaser_driver} for P{position}.",
                "Pressure's building on {leader_driver} — {chaser_driver} right there.",
                "The gap's coming down. {gap} seconds, P{position}.",
                "{chaser_driver}'s in DRS range of {leader_driver}. Game on.",
                "Lovely battle brewing for P{position}.",
                "{leader_driver} under real threat now — {chaser_driver}, {gap} seconds.",
            ],
            "accident_suspected": [
                "Oh, and {driver}'s stopped. That doesn't look good.",
                "{driver}'s pulled up — trouble, clearly.",
                "Hang on, {driver}'s come to a halt on track.",
                "That's {driver} parked. Mechanical, by the looks.",
                "Accident! {driver}'s in the barriers!",
                "Oh no — {driver}'s crashed out.",
                "{driver}'s lost it and he's into the gravel.",
                "That's a heavy one for {driver}.",
                "Contact, contact — {driver}'s out.",
                "{driver}'s in the wall. Race over for him.",
                "Huge moment, that — {driver} off.",
                "{driver} spins it, straight into the run-off.",
                "Disaster for {driver} — that's his race done.",
                "Proper accident, that — {driver} hard into the barrier.",
                "{driver}'s beached in the gravel trap.",
                "Heartbreak — {driver} stopped, smoke coming out.",
                "{driver}'s straight on at the chicane. Stuck.",
                "That is the end of the road for {driver}.",
            ],
            "laps_to_go": [
                "{laps} to go — here comes the business end.",
                "Final stages now — {laps} laps left.",
                "{laps} laps to run. Strategy versus pace.",
                "We're down to {laps}. Tension building.",
                "{laps} to go, and it's getting spicy.",
                "{laps} laps on the board. Time's running out.",
            ],
            "checkered": [
                "And he takes the chequered flag!",
                "Across the line — race over!",
                "Chequered flag falls — what a race.",
                "They take the flag — race done.",
            ],
        },
        # -----------------------------------------------------------
        # PRACTICE — calmer, analytical, no drama
        # -----------------------------------------------------------
        "practice": {
            "overtake": [
                "{driver} clears a slower car — now running in clean air.",
                "Bit of traffic sorted for {driver}, up to P{to_pos}.",
                "{driver} past the queue, finally gets a clear lap.",
                "Traffic management, nothing more — {driver}, P{to_pos}.",
                "{driver} picks his way through, up to P{to_pos}.",
            ],
            "pit_entry": [
                "{driver} back in — time for a look at the data.",
                "In comes {driver}, probably a setup change.",
                "{driver}'s done his run — peeling into the garage.",
                "Back to the box for {driver}, engineers will want a chat.",
                "{driver} in. Expect fresh tyres or a tweak.",
            ],
            "pit_exit": [
                "{driver} heading back out — new run plan.",
                "Out goes {driver} again, more laps to come.",
                "{driver} rolling out of the garage.",
                "Fresh set for {driver}, let's see the pace.",
                "{driver}'s back on track, push lap coming up perhaps.",
            ],
            "fastest_lap": [
                "Nice reference lap from {driver} — {time}.",
                "{driver} tops the timesheets, {time}. Still plenty to come.",
                "Good benchmark that — {driver}, {time}.",
                "{driver} shows a hint of the pace: {time}.",
                "Times are coming down — {driver}, {time}.",
                "Early marker from {driver}: {time}.",
            ],
            "flag_green": [
                "Green light at the end of the pit lane — session is live.",
                "We're green. Cars starting to file out.",
                "Pit exit open, practice is under way.",
            ],
            "flag_yellow": [
                "Yellow in the sector — someone's in trouble.",
                "Yellows out. Someone's had a moment.",
                "Caution flag — eyes up.",
            ],
            "flag_red": [
                "Red flag — session paused.",
                "That'll be a red. Back to the pits.",
                "Session halted, red flag out.",
            ],
            "accident_suspected": [
                "{driver} has stopped on track — could be a gearbox or similar.",
                "Looks like a problem for {driver}, pulled off the line.",
                "{driver} parked up — probably just a precaution.",
                "{driver} in the run-off — small moment, no drama.",
                "{driver} has found the gravel. Not ideal.",
            ],
            "battle": [
                "{chaser_driver} is on a push lap behind {leader_driver} — traffic.",
                "Tricky one, that — {chaser_driver} catching {leader_driver} on a flying lap.",
                "{chaser_driver} will want {leader_driver} out of the way.",
            ],
        },
        # -----------------------------------------------------------
        # QUALIFYING — tense, urgent, lap-focused
        # -----------------------------------------------------------
        "qualifying": {
            "overtake": [
                "{driver} through the traffic, up to P{to_pos} on the timesheets.",
                "Provisional P{to_pos} for {driver} — lap time's gone in.",
                "Times on the board — {driver}, P{to_pos}.",
                "{driver} jumps to P{to_pos} with that one.",
                "Bigger lap than expected — {driver}, P{to_pos}.",
            ],
            "pit_entry": [
                "{driver} back in — that's his first run banked.",
                "{driver} peels off, quick turnaround coming.",
                "In comes {driver}, fresh set of softs next.",
                "{driver} calls it — into the box, save the tyres.",
                "Pit lane for {driver}. Do they have enough left?",
            ],
            "pit_exit": [
                "{driver} out for the flyer — this is the one.",
                "Out goes {driver}, final attempt.",
                "{driver} back on track — last chance for pole.",
                "New tyres, clean air — {driver}'s away.",
                "{driver} pushes out of the pits. All or nothing.",
            ],
            "fastest_lap": [
                "Provisional pole! {driver} — {time}!",
                "{driver} goes top — {time}. Stunner.",
                "Purple everywhere — {driver}, {time}!",
                "That is a serious lap — {driver}, {time}.",
                "{driver} pips it — {time}, new benchmark.",
                "Look at that — {driver}, {time}. Fastest of all.",
                "{driver} delivers when it counts — {time}.",
            ],
            "flag_green": [
                "Session is live — out they come.",
                "Pit exit green, qualifying under way.",
                "We're go — get a lap in.",
            ],
            "flag_yellow": [
                "Yellows — and someone's lap is ruined.",
                "Yellow flag — drivers are going to have to back off.",
                "That's going to cost somebody a time — yellows out.",
            ],
            "flag_red": [
                "Red flag! Session stopped — will they get another run?",
                "Red flag — this could be costly for those still on the lap.",
                "That's a red. Bad news for anyone mid-flyer.",
            ],
            "accident_suspected": [
                "{driver}'s crashed! That's his qualifying done.",
                "Huge — {driver} into the wall on his lap.",
                "{driver} loses it, and that's going to bring the yellows out.",
                "{driver}'s session ends in the barriers.",
                "Oh, {driver} — he's thrown it away.",
            ],
            "battle": [
                "{chaser_driver} catching {leader_driver} — and he's on a hot lap.",
                "Traffic drama — {chaser_driver} closing fast on {leader_driver}.",
                "{leader_driver}'s on the cool-down, {chaser_driver} wants past.",
            ],
        },
    },
    # ---------------------------------------------------------------
    # PORTUGUESE (PT-PT, F1 vocab)
    # ---------------------------------------------------------------
    "pt": {
        "race": {
            "overtake": [
                "E ai esta — {driver}, sobe para P{to_pos}!",
                "Bela manobra de {driver}, ja esta em P{to_pos}.",
                "{driver} mete-o por dentro — P{to_pos}, sem contemplacoes.",
                "Opa, que jeito — {driver} em P{to_pos}.",
                "{driver} nao perdoa, P{to_pos} e dele.",
                "Travagem a fundo e {driver} leva P{to_pos}.",
                "Olha so, {driver} sobe ate P{to_pos}.",
                "De P{from_pos} para P{to_pos} — {driver} em grande.",
                "Com DRS, {driver} vai la e fica com P{to_pos}.",
                "Trabalho feito — {driver}, P{to_pos}.",
                "Coragem, essa — {driver} leva P{to_pos}.",
                "{driver} esta imparavel, agora P{to_pos}.",
                "Manobra limpa de {driver}, P{to_pos} garantido.",
                "Por dentro, bem travado — {driver}, P{to_pos}.",
            ],
            "pit_entry": [
                "E la vem {driver} — box, box.",
                "{driver} ja teve que chegue daqueles pneus, vai entrar.",
                "{driver} desvia para a pit lane.",
                "Entrada nas boxes para {driver} — pode ser undercut.",
                "La vai {driver} para a pit lane, grande aposta.",
                "Estrategia a decorrer — {driver} nas boxes.",
                "Paragem para {driver}, abandona a posicao.",
                "{driver} a entrar — vamos ver que pneu metem.",
            ],
            "pit_exit": [
                "E {driver} esta de volta, borracha nova.",
                "Sai {driver}, pareceu tudo limpo.",
                "{driver} reentra — agora e ver em que posicao fica.",
                "Pneus postos — {driver} la vai ele.",
                "A todo o gas, {driver} sai da pit lane.",
                "{driver} de volta ao combate, pneus frescos.",
                "Paragem feita, {driver} segue em frente.",
                "Grande trabalho da equipa — {driver} la vai.",
            ],
            "fastest_lap": [
                "Ui, roxo por todo o lado — {driver}, {time}!",
                "Volta mais rapida, {driver} em {time}. Que belo.",
                "{driver} a iluminar os ecras — {time}.",
                "Tempo de referencia, {driver}, {time}.",
                "Mas de onde veio isto? {driver} em {time}.",
                "{time} para {driver}. Esta a encontrar tempo em todo o lado.",
                "Roxo, roxo, roxo — {driver}, {time}.",
                "Volta rapida para {driver}, {time}.",
            ],
            "lead_change": [
                "Temos novo lider! {new_driver} passa {old_driver}!",
                "Conseguiu — {new_driver} na lideranca!",
                "A ultrapassagem pela vitoria — {new_driver} a frente.",
                "Adeus {old_driver}, ola {new_driver}.",
                "{new_driver} destrona {old_driver}!",
                "Em P1 — {new_driver}. Grande momento.",
                "Troca no topo! {new_driver} lidera.",
            ],
            "flag_green": [
                "Bandeira verde — e la vamos nos outra vez.",
                "Pista livre, a correr.",
                "Verde outra vez — vamos la.",
                "Tudo limpo agora, a pleno gas.",
            ],
            "flag_yellow": [
                "Amarelas — atencao, pilotos.",
                "Dupla amarela — algo aconteceu.",
                "Cuidado, amarela no sector.",
                "Amarela no ar — aliviar a carga.",
            ],
            "flag_red": [
                "Bandeira vermelha. Sessao parada.",
                "E vermelha — regresso as boxes.",
                "Vermelha. Coisa seria.",
                "Tudo parado — vermelha.",
            ],
            "flag_blue": [
                "Azuis — tem que dar passagem.",
                "Azul, lideres a chegar.",
                "Trafego — azul para o retardatario.",
            ],
            "flag_white": [
                "Branca — carro lento a frente.",
                "Cuidado, branca, alguem a rastejar.",
            ],
            "flag_checkered": [
                "E cai a xadrezada!",
                "Ai esta — bandeira de xadrez!",
                "Cruza a meta — xadrezada!",
            ],
            "flag_generic": [
                "Mudanca de bandeira — {flag}.",
                "{flag} no ar. Atencao.",
            ],
            "race_start": [
                "Luzes apagadas, e la vao eles!",
                "E luzes apagadas — estao a correr!",
                "La vao eles, la vao eles!",
                "Cinco luzes vermelhas — apagam-se — temos corrida!",
                "La vao eles, para a curva um.",
                "Arranque limpo e corrida em andamento.",
            ],
            "battle": [
                "Roda com roda por P{position} — {leader_driver} a aguentar {chaser_driver}, {gap} segundos.",
                "Luta renhida — {chaser_driver} colado a {leader_driver}.",
                "So {gap} segundos entre {leader_driver} e {chaser_driver} em P{position}.",
                "Pressao em cima de {leader_driver} — {chaser_driver} ali mesmo.",
                "A diferenca cai. {gap} segundos, P{position}.",
                "{chaser_driver} no DRS de {leader_driver}.",
                "Bela luta a brotar por P{position}.",
            ],
            "accident_suspected": [
                "Ih, {driver} parou. Nao parece bom.",
                "{driver} ficou para tras — problema, claramente.",
                "Espera — {driver} ficou parado em pista.",
                "Parou {driver}, parece mecanica.",
                "Acidente! {driver} contra as barreiras!",
                "Oh nao — {driver} despistou-se.",
                "{driver} perde o controlo e vai a gravilha.",
                "Grande pancada, essa — {driver}.",
                "Choque! {driver} fora.",
                "{driver} no muro. Corrida terminada.",
                "Grande momento, esse — {driver} fora.",
                "{driver} roda e vai parar ao escape.",
                "Desastre para {driver} — corrida acabada.",
                "Acidente a serio — {driver} forte contra o rail.",
                "{driver} atolado na gravilha.",
                "Desgosto — {driver} parado, sai fumo.",
            ],
            "laps_to_go": [
                "{laps} voltas — chega a hora da verdade.",
                "Reta final — {laps} voltas.",
                "{laps} voltas a espera. Estrategia contra ritmo.",
                "Restam {laps}. Tensao a subir.",
                "{laps} para andar, a coisa aquece.",
                "{laps} voltas no quadro. O tempo foge.",
            ],
            "checkered": [
                "E cai a xadrezada!",
                "Cruza a meta — corrida terminada!",
                "Xadrezada — que corrida!",
            ],
        },
        "practice": {
            "overtake": [
                "{driver} passa um mais lento — ar limpo agora.",
                "Trafego resolvido para {driver}, P{to_pos}.",
                "{driver} finalmente com pista livre, sobe a P{to_pos}.",
                "So gestao de trafego — {driver}, P{to_pos}.",
            ],
            "pit_entry": [
                "{driver} volta as boxes — vao ver a telemetria.",
                "La entra {driver}, acerto de setup provavelmente.",
                "Fim de run para {driver} — regressa a garagem.",
                "{driver} nas boxes, engenheiros vao querer conversa.",
            ],
            "pit_exit": [
                "{driver} de volta a pista — novo plano.",
                "{driver} sai outra vez, mais voltas ai vem.",
                "{driver} sai da garagem, a rolar.",
                "Pneus novos para {driver}, vamos ver o ritmo.",
            ],
            "fastest_lap": [
                "Boa referencia para {driver} — {time}.",
                "{driver} lidera os tempos, {time}. Ainda ha mais.",
                "Bom tempo de referencia — {driver}, {time}.",
                "{driver} mostra o ritmo: {time}.",
            ],
            "flag_green": [
                "Verde na saida das boxes — sessao ao vivo.",
                "Estamos em verde. Carros a sair.",
                "Pit lane aberta, treino comecou.",
            ],
            "flag_yellow": [
                "Amarela no sector — alguem teve um problema.",
                "Amarelas no ar. Alguem se assustou.",
            ],
            "flag_red": [
                "Vermelha — sessao interrompida.",
                "Sera vermelha. De regresso as boxes.",
            ],
            "accident_suspected": [
                "{driver} parou em pista — pode ser caixa ou algo assim.",
                "Parece problema para {driver}, tirou-se da linha.",
                "{driver} imobilizado — possivelmente so precaucao.",
                "{driver} no escape — pequeno momento, sem drama.",
            ],
            "battle": [
                "{chaser_driver} numa volta rapida atras de {leader_driver} — trafego.",
                "Complicado — {chaser_driver} apanha {leader_driver} em push lap.",
            ],
        },
        "qualifying": {
            "overtake": [
                "{driver} passa o trafego, sobe a P{to_pos} nos tempos.",
                "P{to_pos} provisorio para {driver} — tempo registado.",
                "Tempos a mudar — {driver}, P{to_pos}.",
                "{driver} salta para P{to_pos} com essa volta.",
            ],
            "pit_entry": [
                "{driver} de volta — primeira tentativa no bolso.",
                "{driver} desvia, rotacao rapida a caminho.",
                "La entra {driver}, set de macios a seguir.",
                "{driver} encerra o run — poupar o pneu.",
            ],
            "pit_exit": [
                "{driver} para a volta decisiva — e esta.",
                "La vai {driver}, ultima tentativa.",
                "{driver} de volta a pista — ultima chance pela pole.",
                "Pneus novos, ar limpo — {driver} la vai.",
            ],
            "fastest_lap": [
                "Pole provisoria! {driver} — {time}!",
                "{driver} passa para o topo — {time}. Que volta.",
                "Roxo em todo o lado — {driver}, {time}!",
                "Volta seria, essa — {driver}, {time}.",
                "{driver} responde quando e preciso — {time}.",
            ],
            "flag_green": [
                "Sessao ao vivo — saem para a pista.",
                "Pit lane em verde, qualificacao a decorrer.",
                "Vamos la — tempo no cronometro.",
            ],
            "flag_yellow": [
                "Amarelas — e a volta de alguem vai por agua abaixo.",
                "Amarela — vao ter que levantar o pe.",
                "Isto vai custar o tempo a alguem — amarelas.",
            ],
            "flag_red": [
                "Bandeira vermelha! Tera alguem outra tentativa?",
                "Vermelha — pode ser caro para quem estava a fazer volta.",
                "Esta e vermelha. Ma noticia a meio do flyer.",
            ],
            "accident_suspected": [
                "{driver} bateu! Qualificacao acabada para ele.",
                "Enorme — {driver} contra o muro durante a volta.",
                "{driver} perde-o e vai trazer as amarelas.",
                "Sessao de {driver} termina nas barreiras.",
            ],
            "battle": [
                "{chaser_driver} apanha {leader_driver} — em volta lancada.",
                "Drama de trafego — {chaser_driver} fecha rapido sobre {leader_driver}.",
            ],
        },
    },
    # ---------------------------------------------------------------
    # SPANISH  (peninsular, F1)
    # ---------------------------------------------------------------
    "es": {
        "race": {
            "overtake": [
                "Y ahi esta — {driver}, sube a P{to_pos}!",
                "Bonita maniobra de {driver}, ya esta en P{to_pos}.",
                "{driver} lo mete por dentro — P{to_pos}, asi sin mas.",
                "Anda, que bueno — {driver} en P{to_pos}.",
                "{driver} no perdona, P{to_pos} es suyo.",
                "Frenada fuerte y {driver} se queda con P{to_pos}.",
                "Mira eso, {driver} sube hasta P{to_pos}.",
                "De P{from_pos} a P{to_pos} — {driver} de otro planeta.",
                "Con DRS, {driver} se lo lleva — P{to_pos}.",
                "Trabajo hecho — {driver}, P{to_pos}.",
                "Valiente, esa — {driver} P{to_pos}.",
                "{driver} esta imparable, P{to_pos}.",
                "Adelantamiento limpio de {driver}, P{to_pos}.",
            ],
            "pit_entry": [
                "Y aqui llega {driver} — box, box.",
                "{driver} ya ha tenido bastante con esos neumaticos.",
                "{driver} se desvia al pit lane.",
                "Entrada a boxes para {driver} — quiza undercut.",
                "Ahi va {driver} a pit lane, gran apuesta.",
                "Estrategia — {driver} a boxes.",
                "Parada para {driver}, renuncia a la posicion.",
            ],
            "pit_exit": [
                "Y {driver} esta de vuelta, gomas nuevas.",
                "Sale {driver}, todo limpio por lo que parece.",
                "{driver} reincorporado — veamos en que puesto.",
                "Ruedas puestas — {driver} a por ellos.",
                "A tope {driver} saliendo del pit lane.",
                "{driver} de vuelta a la pelea, gomas frescas.",
                "Parada hecha, {driver} sigue adelante.",
            ],
            "fastest_lap": [
                "Uy, morado por todos lados — {driver}, {time}!",
                "Vuelta rapida, {driver} en {time}. Que bueno.",
                "{driver} enciende los cronos — {time}.",
                "Referencia nueva, {driver}, {time}.",
                "Pero de donde ha salido esto? {driver}, {time}.",
                "Un {time} para {driver}. Esta encontrando tiempo.",
                "Morado, morado, morado — {driver}, {time}.",
            ],
            "lead_change": [
                "Tenemos nuevo lider! {new_driver} supera a {old_driver}!",
                "Lo ha hecho — {new_driver} en cabeza!",
                "El adelantamiento por la victoria — {new_driver} al frente.",
                "Adios {old_driver}, hola {new_driver}.",
                "{new_driver} destrona a {old_driver}!",
                "En P1 — {new_driver}. Gran momento.",
                "Cambio al frente! {new_driver} lidera.",
            ],
            "flag_green": [
                "Verde — y alla vamos de nuevo.",
                "Pista libre, a correr.",
                "Verde otra vez — vamos alla.",
                "Todo limpio, a tope.",
            ],
            "flag_yellow": [
                "Amarillas — atentos, pilotos.",
                "Doble amarilla — algo ha pasado.",
                "Cuidado, amarilla en sector.",
                "Amarilla — levantar el pie.",
            ],
            "flag_red": [
                "Bandera roja. Sesion detenida.",
                "Es roja — de vuelta a boxes.",
                "Roja. Algo serio.",
                "Todo parado — roja.",
            ],
            "flag_blue": [
                "Azules — tiene que dejar pasar.",
                "Azul, lideres llegando.",
                "Trafico — azul para el rezagado.",
            ],
            "flag_white": [
                "Blanca — coche lento delante.",
                "Cuidado, blanca, alguien arrastrandose.",
            ],
            "flag_checkered": [
                "Y cae la bandera a cuadros!",
                "Ahi esta — bandera de cuadros!",
                "Cruza la meta — cuadros!",
            ],
            "flag_generic": [
                "Cambio de bandera — {flag}.",
                "{flag} al aire. Atentos.",
            ],
            "race_start": [
                "Se apagan las luces, y alla van!",
                "Luces fuera — arranca la carrera!",
                "Alla van, alla van!",
                "Cinco rojas — se apagan — carrera en marcha!",
                "A por la curva uno!",
                "Salida limpia y carrera en marcha.",
            ],
            "battle": [
                "Rueda con rueda por P{position} — {leader_driver} aguantando a {chaser_driver}, {gap} segundos.",
                "Buena pelea — {chaser_driver} pegado a {leader_driver}.",
                "Solo {gap} segundos entre {leader_driver} y {chaser_driver} por P{position}.",
                "Presion para {leader_driver} — {chaser_driver} ahi mismo.",
                "La diferencia baja. {gap} segundos, P{position}.",
                "{chaser_driver} en DRS de {leader_driver}.",
                "Duelo interesante por P{position}.",
            ],
            "accident_suspected": [
                "Anda, {driver} se ha parado. Mala pinta.",
                "{driver} se ha quedado — problema, esta claro.",
                "Espera — {driver} detenido en pista.",
                "{driver} parado, parece mecanica.",
                "Accidente! {driver} contra las barreras!",
                "Oh no — {driver} se ha estrellado.",
                "{driver} pierde el control y a la grava.",
                "Menudo golpe, ese — {driver}.",
                "Contacto! {driver} fuera.",
                "{driver} contra el muro. Carrera terminada.",
                "Momentazo — {driver} fuera.",
                "{driver} trompea y queda en el escape.",
                "Desastre para {driver} — fin de carrera.",
                "Accidente serio — {driver} con fuerza contra el rail.",
                "{driver} atrapado en la grava.",
            ],
            "laps_to_go": [
                "{laps} vueltas — llega la hora de la verdad.",
                "Recta final — {laps} vueltas.",
                "{laps} vueltas por delante. Estrategia contra ritmo.",
                "Quedan {laps}. Tension maxima.",
                "{laps} por rodar, la cosa se pone caliente.",
                "{laps} en el panel. El tiempo se acaba.",
            ],
            "checkered": [
                "Y cae la bandera a cuadros!",
                "Cruza la meta — fin de carrera!",
                "Cuadros — que carrera!",
            ],
        },
        "practice": {
            "overtake": [
                "{driver} pasa a uno mas lento — aire limpio ahora.",
                "Trafico resuelto para {driver}, P{to_pos}.",
                "{driver} por fin con pista libre, P{to_pos}.",
                "Solo gestion de trafico — {driver}, P{to_pos}.",
            ],
            "pit_entry": [
                "{driver} vuelve al box — a revisar datos.",
                "Ahi entra {driver}, cambio de setup probablemente.",
                "{driver} termina el run — vuelve al garaje.",
                "{driver} a boxes, ingenieros querran hablar.",
            ],
            "pit_exit": [
                "{driver} de vuelta a pista — nuevo plan.",
                "{driver} sale otra vez, mas vueltas por delante.",
                "{driver} sale del garaje, rodando.",
                "Neumaticos nuevos para {driver}, veamos el ritmo.",
            ],
            "fastest_lap": [
                "Buena referencia de {driver} — {time}.",
                "{driver} lidera los tiempos, {time}. Aun queda mas.",
                "Buen tiempo de referencia — {driver}, {time}.",
                "{driver} muestra el ritmo: {time}.",
            ],
            "flag_green": [
                "Verde a la salida del pit lane — sesion en marcha.",
                "Estamos en verde. Coches saliendo.",
                "Pit lane abierto, entrenamiento en marcha.",
            ],
            "flag_yellow": [
                "Amarilla en sector — alguien ha tenido un problema.",
                "Amarillas al aire. Alguien se ha asustado.",
            ],
            "flag_red": [
                "Roja — sesion interrumpida.",
                "Sera roja. De vuelta a boxes.",
            ],
            "accident_suspected": [
                "{driver} parado en pista — puede ser caja o similar.",
                "Parece problema para {driver}, fuera de la linea.",
                "{driver} detenido — probablemente precaucion.",
                "{driver} en el escape — momento pequeno, sin drama.",
            ],
            "battle": [
                "{chaser_driver} en vuelta rapida tras {leader_driver} — trafico.",
                "Lio — {chaser_driver} pilla a {leader_driver} en push lap.",
            ],
        },
        "qualifying": {
            "overtake": [
                "{driver} pasa el trafico, sube a P{to_pos} en los tiempos.",
                "P{to_pos} provisional para {driver} — tiempo registrado.",
                "Tiempos cambiando — {driver}, P{to_pos}.",
                "{driver} salta a P{to_pos} con esa vuelta.",
            ],
            "pit_entry": [
                "{driver} de vuelta — primer intento guardado.",
                "{driver} se desvia, rotacion rapida.",
                "Ahi entra {driver}, set de blandos a continuacion.",
                "{driver} cierra el run — cuidar el neumatico.",
            ],
            "pit_exit": [
                "{driver} para la vuelta decisiva — esta es.",
                "Ahi va {driver}, ultimo intento.",
                "{driver} de vuelta — ultima oportunidad por la pole.",
                "Neumaticos nuevos, aire limpio — {driver} se lanza.",
            ],
            "fastest_lap": [
                "Pole provisional! {driver} — {time}!",
                "{driver} pasa arriba — {time}. Vuelton.",
                "Morado por todos lados — {driver}, {time}!",
                "Vuelta seria, esa — {driver}, {time}.",
                "{driver} responde cuando toca — {time}.",
            ],
            "flag_green": [
                "Sesion en marcha — salen a pista.",
                "Pit lane en verde, clasificacion en marcha.",
                "Vamos — tiempos al cronometro.",
            ],
            "flag_yellow": [
                "Amarillas — la vuelta de alguien se va al traste.",
                "Amarilla — tendran que levantar.",
                "Esto le va a costar a alguien — amarillas.",
            ],
            "flag_red": [
                "Roja! Tendra alguien otra oportunidad?",
                "Roja — puede ser caro para quien estuviera en vuelta.",
                "Esta es roja. Mala noticia a mitad de flyer.",
            ],
            "accident_suspected": [
                "{driver} se ha estrellado! Clasi acabada para el.",
                "Enorme — {driver} contra el muro en su vuelta.",
                "{driver} lo pierde, y traera las amarillas.",
                "Sesion de {driver} termina en las barreras.",
            ],
            "battle": [
                "{chaser_driver} pilla a {leader_driver} — en vuelta lanzada.",
                "Drama de trafico — {chaser_driver} cerrando sobre {leader_driver}.",
            ],
        },
    },
    # ---------------------------------------------------------------
    # JAPANESE
    # ---------------------------------------------------------------
    "jp": {
        "race": {
            "overtake": [
                "さあ、{driver}がP{to_pos}に上がった！",
                "見事な仕掛け！{driver}、P{to_pos}です。",
                "{driver}、インから刺してP{to_pos}。",
                "おっと、{driver}が決めました、P{to_pos}。",
                "これは勇気ある一手、{driver}がP{to_pos}。",
                "{driver}、止まりませんね、P{to_pos}へ。",
                "P{from_pos}からP{to_pos}へ、{driver}絶好調です。",
                "DRSを使って{driver}、P{to_pos}獲得。",
                "綺麗にまとめましたね、{driver}、P{to_pos}。",
                "鋭いブレーキング、{driver}がP{to_pos}。",
                "ついに行きました、{driver}、P{to_pos}。",
            ],
            "pit_entry": [
                "さあ、{driver}がピットに入ってきます。",
                "{driver}、もうタイヤが限界のようです。",
                "ボックス、ボックス — {driver}。",
                "{driver}、戦略が動きます。ピットイン。",
                "アンダーカット狙いか、{driver}がピットへ。",
                "ポジションを捨てて、{driver}が入る。",
                "{driver}、ピットレーンへ飛び込みました。",
            ],
            "pit_exit": [
                "{driver}、新品タイヤで戻ってきました。",
                "クリーンなストップ、{driver}復帰。",
                "{driver}がピットアウト、どこに戻れるか。",
                "タイヤを履き替えて、{driver}が再び加速。",
                "{driver}、再びバトルの中へ。",
                "素晴らしい作業、{driver}が飛び出します。",
                "作業完了、{driver}がコース復帰。",
            ],
            "fastest_lap": [
                "おっと、パープル続出 — {driver}、{time}！",
                "ファステストラップ、{driver}の{time}です。",
                "{driver}、タイムシートのトップへ、{time}。",
                "基準タイム更新、{driver}の{time}。",
                "どこから出したのか、{driver}の{time}。",
                "{time}を叩き出した{driver}、絶好調。",
            ],
            "lead_change": [
                "トップが変わった！{new_driver}が{old_driver}を抜いた！",
                "やりました、{new_driver}がトップに！",
                "優勝争いでの一発 — {new_driver}が先頭。",
                "さようなら{old_driver}、{new_driver}がリード。",
                "{new_driver}、ついに{old_driver}を攻略。",
                "首位に立ったのは{new_driver}、大きな瞬間です。",
            ],
            "flag_green": [
                "グリーンフラッグ、再びレース開始です。",
                "コースクリア、走行再開。",
                "グリーンです、肘を張って。",
                "全て解除、グリーン。",
            ],
            "flag_yellow": [
                "イエロー、ドライバーは注意。",
                "ダブルイエロー — 何かが起きた。",
                "セクターにイエロー、慎重に。",
                "イエローフラッグ、ペースダウン。",
            ],
            "flag_red": [
                "赤旗、セッション中断です。",
                "これは赤旗 — 全車ピットへ。",
                "赤旗、深刻な状況です。",
                "走行停止、赤旗提示。",
            ],
            "flag_blue": [
                "ブルーフラッグ — 譲らないと。",
                "ブルー、先頭集団が来ます。",
                "周回遅れにブルー。",
            ],
            "flag_white": [
                "ホワイトフラッグ — 低速車あり。",
                "注意、低速車が前方に。",
            ],
            "flag_checkered": [
                "チェッカードフラッグが振られました！",
                "ゴール — チェッカー！",
                "ラインを越えて、チェッカーフラッグ！",
            ],
            "flag_generic": [
                "フラッグ変化 — {flag}。",
                "{flag}フラッグ提示、注意。",
            ],
            "race_start": [
                "ライトアウト、レーススタート！",
                "シグナル消灯、スタート！",
                "さあ、行きました、行きました！",
                "5つのライトが消えた — レース開始！",
                "ターン1に向かってオープニングラップ！",
                "クリーンなスタート、レースが動き出します。",
            ],
            "battle": [
                "P{position}争い — {leader_driver}が{chaser_driver}を抑える、差は{gap}秒。",
                "激しい攻防、{chaser_driver}が{leader_driver}の真後ろに。",
                "わずか{gap}秒、P{position}をめぐる戦い。",
                "{leader_driver}にプレッシャー、{chaser_driver}が迫ります。",
                "差が縮まる、{gap}秒、P{position}。",
                "{chaser_driver}、DRS圏内へ。",
            ],
            "accident_suspected": [
                "おっと、{driver}が止まった、嫌な予感。",
                "{driver}、停止 — 明らかにトラブルです。",
                "{driver}、コース上で動かなくなりました。",
                "{driver}のマシンが止まる、機械的なものか。",
                "アクシデント！{driver}がバリアに！",
                "なんと — {driver}がクラッシュ。",
                "{driver}、コントロールを失いグラベルへ。",
                "{driver}に大きな衝撃、レースアウト。",
                "接触！{driver}、ここで終わり。",
                "{driver}、ウォールに激突、レース終了。",
                "大きな瞬間、{driver}がコースアウト。",
                "{driver}、スピンしてランオフに。",
                "{driver}にとって大惨事 — ここで終わり。",
                "{driver}、タイヤバリアに突っ込んで終わり。",
            ],
            "laps_to_go": [
                "残り{laps}周 — いよいよ正念場。",
                "ファイナルステージ、あと{laps}周。",
                "{laps}周、戦略か純粋なペースか。",
                "残り{laps}周、緊張が高まります。",
                "あと{laps}、時間がありません。",
            ],
            "checkered": [
                "チェッカーを受けました！",
                "ゴール — レース終了！",
                "チェッカー、素晴らしいレースでした。",
            ],
        },
        "practice": {
            "overtake": [
                "{driver}、遅いマシンをパス、クリアな空気へ。",
                "トラフィック処理、{driver}がP{to_pos}。",
                "{driver}、やっとクリアラップを取れます。",
                "順位操作ではなく、トラフィックの問題です。",
            ],
            "pit_entry": [
                "{driver}、ピットイン、データ確認でしょう。",
                "セッティング変更か、{driver}がガレージへ。",
                "{driver}、ランを終えてピットへ。",
                "エンジニアと話すためでしょう、{driver}が戻ります。",
            ],
            "pit_exit": [
                "{driver}、再びコースへ — 新しいランプラン。",
                "また走り出しました、{driver}。",
                "{driver}、ガレージからロールアウト。",
                "新品タイヤで{driver}、ペースを見ましょう。",
            ],
            "fastest_lap": [
                "{driver}、良い基準ラップ、{time}。",
                "{driver}、タイムシートでトップ、{time}。まだ余力あり。",
                "良い参考タイム、{driver}、{time}。",
                "{driver}、ペースを示しました、{time}。",
            ],
            "flag_green": [
                "ピット出口グリーン、セッション開始。",
                "グリーンです、マシンが続々と出てきます。",
                "ピットレーンオープン、プラクティス開始。",
            ],
            "flag_yellow": [
                "セクターにイエロー、誰かがトラブル。",
                "イエロー、誰かが一瞬ヒヤリ。",
            ],
            "flag_red": [
                "赤旗、セッション中断。",
                "赤旗のようです、全車ピットへ。",
            ],
            "accident_suspected": [
                "{driver}、コース上で停止 — ギアボックスかも。",
                "{driver}に問題、ラインを外れました。",
                "{driver}、停止、念のためでしょう。",
                "{driver}、ランオフに、小さな瞬間です。",
            ],
            "battle": [
                "{chaser_driver}がプッシュラップ中、トラフィックが。",
                "{chaser_driver}、{leader_driver}に追いつきます、フライングラップ中。",
            ],
        },
        "qualifying": {
            "overtake": [
                "{driver}、トラフィックを抜けてP{to_pos}へ浮上。",
                "暫定P{to_pos}、{driver}のタイムが入りました。",
                "タイムシート更新、{driver}がP{to_pos}。",
                "{driver}、そのラップでP{to_pos}へジャンプ。",
            ],
            "pit_entry": [
                "{driver}、ピットイン、最初のランをまとめました。",
                "{driver}、ピットへ、素早くターンアラウンド。",
                "次は新品ソフトでしょう、{driver}がピットへ。",
                "{driver}、ランを締めて、タイヤを温存。",
            ],
            "pit_exit": [
                "{driver}、アタックに出ます — これが本命。",
                "ラストアタック、{driver}が出ていきます。",
                "{driver}、ポールを狙うラストチャンス。",
                "新品タイヤ、クリアな空気 — {driver}、さあ。",
            ],
            "fastest_lap": [
                "暫定ポール！{driver}、{time}！",
                "{driver}、トップタイム — {time}。素晴らしい。",
                "パープル続出、{driver}、{time}！",
                "これは本物のラップ、{driver}、{time}。",
                "{driver}、ここで仕事をします、{time}。",
            ],
            "flag_green": [
                "セッション開始、出ていきます。",
                "ピット出口グリーン、予選スタート。",
                "さあ、タイムを刻みましょう。",
            ],
            "flag_yellow": [
                "イエロー — 誰かのラップが台無しに。",
                "イエロー、ペースを落とさないと。",
                "これは誰かのタイムを失わせる、イエロー。",
            ],
            "flag_red": [
                "赤旗！もう一回走れるのか？",
                "赤旗、ラップ中だった人には痛い。",
                "赤旗、フライング中は大打撃。",
            ],
            "accident_suspected": [
                "{driver}がクラッシュ、予選終了です。",
                "大きなクラッシュ、{driver}がウォールに。",
                "{driver}、マシンを失い、イエローが出ます。",
                "{driver}のセッションがバリアで終わる。",
            ],
            "battle": [
                "{chaser_driver}が{leader_driver}に接近、アタックラップ中。",
                "トラフィックドラマ、{chaser_driver}が{leader_driver}に迫ります。",
            ],
        },
    },
}


def _event_key(event: dict) -> str:
    """Map an event dict to a template key."""
    t = (event.get("type") or "").lower()
    if t == "flag_change":
        return _flag_key(event.get("flag", ""))
    return t


class TemplateCommentator:
    """Offline commentary generator — no network, no API key.

    `generate(event, language, session_type)` picks a line from the most
    specific pool available, falling back from session-specific to race to
    `flag_generic` to empty string.
    """

    def __init__(self, history_per_tag: int = 8) -> None:
        self._recent: dict[str, deque[str]] = {}
        self._history_per_tag = history_per_tag
        self._rng = random.Random()

    def _pool(self, language: str, session_type: str, key: str) -> list[str]:
        lang = (language or "en").lower()
        lang_pool = TEMPLATES.get(lang) or TEMPLATES["en"]
        s_key = _session_key(session_type)

        # Session-specific pool first
        if s_key in lang_pool:
            pool = lang_pool[s_key].get(key)
            if pool:
                return pool

        # Fall back to race pool
        race_pool = lang_pool.get("race") or {}
        pool = race_pool.get(key)
        if pool:
            return pool

        # Final fallback: generic flag text
        return race_pool.get("flag_generic") or []

    def _pick(self, tag: str, options: Iterable[str]) -> str:
        opts = list(options)
        if not opts:
            return ""
        recent = self._recent.setdefault(tag, deque(maxlen=self._history_per_tag))
        pool = [o for o in opts if o not in recent] or opts
        choice = self._rng.choice(pool)
        recent.append(choice)
        return choice

    def generate_filler(self, subject: dict, language: str = "en") -> str:
        """Offline filler: a single parameterized line about a driver or track.

        Subject shape: {"kind": "driver"|"track", "data": {...}}. Missing
        fields are tolerated — the line is stitched from whatever is available.
        """
        if not subject:
            return ""
        data = subject.get("data") or {}
        kind = subject.get("kind") or "driver"
        lang = (language or "en").lower()

        def pick(en: str, pt: str, es: str, jp: str) -> str:
            return {"en": en, "pt": pt, "es": es, "jp": jp}.get(lang, en)

        if kind == "driver":
            name = data.get("name") or data.get("username") or pick(
                "this driver", "este piloto", "este piloto", "このドライバー"
            )
            known = data.get("known_for")
            fun = data.get("fun_fact")
            irating = data.get("irating_peak") or data.get("irating")
            team = data.get("teamname")
            if fun:
                return fun if str(name) in str(fun) else f"{name} — {fun}"
            if known and irating:
                return pick(
                    f"{name} — peak around {irating} iRating, known for {known}.",
                    f"{name} — picos perto de {irating} iRating, conhecido por {known}.",
                    f"{name} — picos cerca de {irating} iRating, conocido por {known}.",
                    f"{name} — ピークは約{irating} iRating、{known}で知られています。",
                )
            if known:
                return pick(
                    f"{name} — known for {known}.",
                    f"{name} — conhecido por {known}.",
                    f"{name} — conocido por {known}.",
                    f"{name} — {known}で知られています。",
                )
            if team:
                return pick(
                    f"{name} out there for {team} today.",
                    f"{name} em pista pela {team} hoje.",
                    f"{name} en pista con {team} hoy.",
                    f"{name}、今日は{team}で走っています。",
                )
            return pick(
                f"Keeping an eye on {name} out there.",
                f"De olho em {name} na pista.",
                f"Atentos a {name} en pista.",
                f"{name}の走りに注目しましょう。",
            )

        # Track
        tname = data.get("name") or pick(
            "this circuit", "este circuito", "este circuito", "このサーキット"
        )
        length = data.get("length_km")
        corners = data.get("corners")
        record = data.get("lap_record")
        fun = data.get("fun_fact")
        if fun:
            return fun if str(tname) in str(fun) else f"{tname} — {fun}"
        if length and corners:
            return pick(
                f"Reminder, {tname} runs {length} km across {corners} corners.",
                f"Recorda, {tname} tem {length} km com {corners} curvas.",
                f"Recuerda, {tname} son {length} km y {corners} curvas.",
                f"思い出してください、{tname}は{length}kmで{corners}コーナーです。",
            )
        if record:
            return pick(
                f"Lap record around {tname} stands at {record}.",
                f"O recorde de volta em {tname} esta em {record}.",
                f"El record de vuelta en {tname} es de {record}.",
                f"{tname}のラップレコードは{record}です。",
            )
        return pick(
            f"Plenty of history at {tname}.",
            f"Muita historia em {tname}.",
            f"Mucha historia en {tname}.",
            f"{tname}には多くの歴史があります。",
        )

    def generate(self, event: dict, language: str = "en", session_type: str = "race") -> str:
        """Return a single broadcast-style line for the given event.

        `session_type` is a free-form string (e.g. "Race", "Qualify 2",
        "Practice"). It's normalized internally to one of practice /
        qualifying / race.
        """
        if not event:
            return ""
        key = _event_key(event)
        s_key = _session_key(session_type)
        tag = f"{language}:{s_key}:{key}"
        template = self._pick(tag, self._pool(language, session_type, key))
        if not template:
            return ""
        try:
            return template.format_map(_SafeDict(event))
        except Exception:
            return template
