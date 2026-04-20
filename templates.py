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
                "Picture-perfect late-braking — {driver}, P{to_pos}.",
                "Commitment! {driver} goes for the gap and it's there. P{to_pos}.",
                "No hesitation from {driver} — straight past for P{to_pos}.",
                "That's the overtake of the race so far. {driver}, P{to_pos}.",
                "Clean, tidy, ruthless — {driver} up to P{to_pos}.",
                "The door opened half a millimetre and {driver} was through. P{to_pos}.",
                "{driver} carries the momentum beautifully — P{to_pos}.",
                "Muscled his way past, has {driver}. P{to_pos}.",
                "Outbraked him completely — {driver}, P{to_pos}.",
                "That's the charge. P{from_pos} to P{to_pos}, {driver}.",
                "He's through on the outside! Bold, bold move. {driver}, P{to_pos}.",
                "You can't leave that gap — and {driver} didn't. P{to_pos}.",
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
                "There's the blink on {driver} — he's in the pit lane.",
                "The tyres were shot — no choice for {driver} there.",
                "{driver} pits — and his rivals will be watching very carefully.",
                "Bold undercut attempt by the {driver} team? Into the pits.",
                "Overcut or undercut? {driver} is stopping right now.",
                "And the decision is made — {driver} in for fresh rubber.",
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
                "Blazing out of the pit box — {driver}'s got a job to do.",
                "The crew nailed that stop. {driver}'s gone.",
                "Fresh tyres, fresh hope — {driver}'s back on it.",
                "Out into clean air, {driver}. Make those tyres sing.",
                "The stopwatch will tell the story — {driver}'s released.",
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
                "All sectors purple — {driver}, {time}. Sensational.",
                "New fastest lap! {driver} smashes the benchmark with {time}.",
                "He is absolutely flying — {driver}, {time}.",
                "That lap is in a different postcode to everyone else. {driver}, {time}.",
                "{driver} on the limit all the way round — {time}.",
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
                "{new_driver} capitalises and heads the field!",
                "Seismic shift at the front — {new_driver} is in the lead.",
                "From behind to out front — {new_driver} leads!",
                "{old_driver} loses position at the top — {new_driver} pounces.",
                "The lead is gone for {old_driver}. {new_driver} heads it now.",
                "Extraordinary — {new_driver} takes control of this race.",
            ],
            "flag_green": [
                "Green flag — and off we go again.",
                "Clear track, we're racing.",
                "Back to green. Elbows out, everyone.",
                "Green, green, green — race is on.",
                "All clear now, back up to speed.",
                "Stewards have cleared it — green flag, let's go.",
                "The race director waves green — they're into it.",
                "Here we go again — green flag!",
                "Full racing conditions restored. Go, go, go.",
                "Track is clear — green light, full attack.",
            ],
            "flag_yellow": [
                "Yellows — heads up, drivers.",
                "Double-waved yellows, something's happened.",
                "Careful now, yellow in the sector.",
                "Yellow flag out — ease it off.",
                "Caution period, yellows flying.",
                "Yellow flag — marshal's post, stay alert.",
                "Slow down, there's been an incident.",
                "Yellows waving — no overtaking through here.",
                "Something's happened in sector — yellow, yellow.",
                "Yellow flag, keep it together through this section.",
            ],
            "flag_red": [
                "Red flag. The session is stopped.",
                "That's a red — back to the pit lane, everyone.",
                "Red flag. Something serious.",
                "All stop — red flag.",
                "We are red flagged. Drivers, pit lane.",
                "Red flag! Slow down and form up safely.",
                "The session has been suspended — red flag.",
                "Everything stops — red flag is out.",
                "Race suspended. Something significant has happened.",
            ],
            "flag_blue": [
                "Blue flags — he needs to move over.",
                "Blues out, leaders coming through.",
                "Traffic — blue flag for the backmarker.",
                "Blue flag, let them by.",
                "Lapped traffic — blue flag, let the leaders through.",
                "Give way! Blue flags shown.",
                "That backmarker needs to be aware — blue flags waving.",
            ],
            "flag_white": [
                "White flag — slow car ahead.",
                "Careful, white flag, someone's crawling.",
                "Slow-moving car — white flag's out.",
                "White flag on display — slow vehicle somewhere on track.",
                "Be alert — white flag, damaged car ahead.",
            ],
            "flag_checkered": [
                "And the chequered flag falls!",
                "There it is — the chequered flag!",
                "Across the line — chequered flag!",
                "The chequered flag waves — it's all over!",
                "Race over — the chequered flag is out!",
            ],
            "flag_generic": [
                "Flag change on circuit — {flag}.",
                "{flag} flag out. Eyes up.",
                "Heads up, {flag} flag showing.",
                "Marshal's post — {flag} flag.",
            ],
            "race_start": [
                "Lights out, and away we go!",
                "It's lights out — they're racing!",
                "Go, go, go — the race is on!",
                "Five red lights — out — and we have a race!",
                "Off they go, into turn one.",
                "Clean getaway and the race is underway.",
                "The boards are up — and they're off!",
                "Race day begins — lights out and here we go!",
                "Into the first braking zone — absolutely flat out!",
                "What a start — everyone seems to have made it cleanly.",
                "Clean start — now it's about strategy and pace.",
                "The lights go out and the season resumes!",
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
                "Nose to tail — {chaser_driver} is all over {leader_driver}.",
                "This is fantastic racing — {leader_driver} and {chaser_driver}, P{position}.",
                "{chaser_driver} is closing — can he find a way past {leader_driver}?",
                "Every single corner, {chaser_driver} is probing. P{position}.",
                "The gap is {gap} — and it is getting smaller.",
                "Point five of a second, P{position}. This is mouth-watering.",
                "{leader_driver} is defending brilliantly but {chaser_driver} won't give up.",
                "Into every braking zone, {chaser_driver} is trying {leader_driver}.",
                "You don't need to be an expert to enjoy this — {leader_driver} and {chaser_driver} for P{position}.",
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
                "Oh, big contact! {driver} punted off.",
                "He's gone. {driver} — that's a retirement.",
                "Understeer into the gravel — {driver} is beached.",
                "Front wing damage for {driver} — he's done.",
                "Wheel-to-wheel contact and {driver} has come off worst.",
                "{driver}'s lost the rear and there's nothing he can do.",
            ],
            "laps_to_go": [
                "{laps} to go — here comes the business end.",
                "Final stages now — {laps} laps left.",
                "{laps} laps to run. Strategy versus pace.",
                "We're down to {laps}. Tension building.",
                "{laps} to go, and it's getting spicy.",
                "{laps} laps on the board. Time's running out.",
                "Just {laps} laps remaining — anything can happen.",
                "{laps} to go — this race is far from over.",
                "Counting down: {laps} laps. Every position matters.",
                "We're in the final {laps} — buckle up.",
            ],
            "checkered": [
                "And he takes the chequered flag!",
                "Across the line — race over!",
                "Chequered flag falls — what a race.",
                "They take the flag — race done.",
                "Brilliant — across the line to take the win!",
                "The flag is out — and what a performance that was.",
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
                "{driver} finds a gap and gets the clean air he was after.",
                "That'll help — {driver} through the traffic, P{to_pos}.",
                "Getting position for the push lap — {driver}, P{to_pos}.",
            ],
            "pit_entry": [
                "{driver} back in — time for a look at the data.",
                "In comes {driver}, probably a setup change.",
                "{driver}'s done his run — peeling into the garage.",
                "Back to the box for {driver}, engineers will want a chat.",
                "{driver} in. Expect fresh tyres or a tweak.",
                "Run's over for {driver} — back to the pit lane.",
                "Engineers pulling {driver} in to check the balance.",
                "{driver} calls it early, wants a setup conversation.",
                "That's the end of the long run — {driver} back in.",
                "Bringing it in to assess tyre wear. {driver} in.",
            ],
            "pit_exit": [
                "{driver} heading back out — new run plan.",
                "Out goes {driver} again, more laps to come.",
                "{driver} rolling out of the garage.",
                "Fresh set for {driver}, let's see the pace.",
                "{driver}'s back on track, push lap coming up perhaps.",
                "{driver} rejoins with an adjusted setup — interesting.",
                "Back on the rubber, {driver}. Let's see the improvement.",
                "Out on the quali simulation now — {driver}.",
                "New tyres, new data — {driver} back out.",
                "{driver} returns. Engineers will be watching closely.",
            ],
            "fastest_lap": [
                "Nice reference lap from {driver} — {time}.",
                "{driver} tops the timesheets, {time}. Still plenty to come.",
                "Good benchmark that — {driver}, {time}.",
                "{driver} shows a hint of the pace: {time}.",
                "Times are coming down — {driver}, {time}.",
                "Early marker from {driver}: {time}.",
                "That's a tidy lap from {driver} — {time} on the board.",
                "Not a qualifying lap, but still — {driver}, {time}.",
                "Solid middle sector was the key — {driver}, {time}.",
                "{driver} on fresh rubber — {time}. Noteworthy.",
                "P1 in practice — {driver}, {time}. Don't read too much in, though.",
                "Quickest so far. {driver}, {time}.",
            ],
            "flag_green": [
                "Green light at the end of the pit lane — session is live.",
                "We're green. Cars starting to file out.",
                "Pit exit open, practice is under way.",
                "Session begins — tyres need warming, so slowly does it initially.",
                "Green flag, and {driver}'s first to head out.",
            ],
            "flag_yellow": [
                "Yellow in the sector — someone's in trouble.",
                "Yellows out. Someone's had a moment.",
                "Caution flag — eyes up.",
                "Yellow flag — somebody's off. Investigation time.",
                "Yellow waving — session may get a bit scrappy.",
            ],
            "flag_red": [
                "Red flag — session paused.",
                "That'll be a red. Back to the pits.",
                "Session halted, red flag out.",
                "Red flag in practice — important running time lost.",
                "That's stopped the session. Red flag.",
            ],
            "accident_suspected": [
                "{driver} has stopped on track — could be a gearbox or similar.",
                "Looks like a problem for {driver}, pulled off the line.",
                "{driver} parked up — probably just a precaution.",
                "{driver} in the run-off — small moment, no drama.",
                "{driver} has found the gravel. Not ideal.",
                "{driver} is stationary — we'll await word from the garage.",
                "Mechanical failure for {driver} perhaps — he's stopped.",
                "Small snap from {driver} — into the grass, but he's okay.",
                "{driver}'s had a moment — off at the exit, back on.",
            ],
            "battle": [
                "{chaser_driver} is on a push lap behind {leader_driver} — traffic.",
                "Tricky one, that — {chaser_driver} catching {leader_driver} on a flying lap.",
                "{chaser_driver} will want {leader_driver} out of the way.",
                "Traffic situation — {chaser_driver} losing time behind {leader_driver}.",
                "That'll cost {chaser_driver} a few tenths — stuck behind {leader_driver}.",
                "{leader_driver} on the out-lap, {chaser_driver} on a hot one. Not ideal.",
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
                "That's good enough for P{to_pos} — {driver} improves.",
                "{driver} goes quicker! P{to_pos} provisionally.",
                "P{to_pos} for {driver} on the timing screens.",
                "Up he goes — {driver}, P{to_pos}. The pressure is on the others.",
                "Personal best sectors add up to P{to_pos} for {driver}.",
            ],
            "pit_entry": [
                "{driver} back in — that's his first run banked.",
                "{driver} peels off, quick turnaround coming.",
                "In comes {driver}, fresh set of softs next.",
                "{driver} calls it — into the box, save the tyres.",
                "Pit lane for {driver}. Do they have enough left?",
                "{driver} pits — that's the banker lap done.",
                "Saving rubber for the final attempt — {driver} in.",
                "{driver} straight into the garage. Fresh rubber imminent.",
                "Back under the covers — {driver}'s not happy with that lap.",
                "Protecting the tyre for one final crack — {driver} in.",
            ],
            "pit_exit": [
                "{driver} out for the flyer — this is the one.",
                "Out goes {driver}, final attempt.",
                "{driver} back on track — last chance for pole.",
                "New tyres, clean air — {driver}'s away.",
                "{driver} pushes out of the pits. All or nothing.",
                "The final run — {driver} launches.",
                "This is it for {driver} — last push lap coming.",
                "There's the green light — {driver}, go!",
                "Fresh softs, clear track — {driver}'s on the move.",
                "Out he goes — {driver} will want purple in all three sectors.",
            ],
            "fastest_lap": [
                "Provisional pole! {driver} — {time}!",
                "{driver} goes top — {time}. Stunner.",
                "Purple everywhere — {driver}, {time}!",
                "That is a serious lap — {driver}, {time}.",
                "{driver} pips it — {time}, new benchmark.",
                "Look at that — {driver}, {time}. Fastest of all.",
                "{driver} delivers when it counts — {time}.",
                "That will take some beating! {driver}, {time}.",
                "He's raised the bar — {driver}, {time}.",
                "Oh, what a lap! {driver} — {time}!",
                "Almost perfect — {driver}, {time}. Provisional pole.",
                "Stunning through the final sector — {driver}, {time}.",
                "{driver} finds the lap when it matters — {time}.",
            ],
            "flag_green": [
                "Session is live — out they come.",
                "Pit exit green, qualifying under way.",
                "We're go — get a lap in.",
                "Qualifying begins — who's first out?",
                "Green flag — the clock is running.",
                "Out they come — every tenth counts now.",
            ],
            "flag_yellow": [
                "Yellows — and someone's lap is ruined.",
                "Yellow flag — drivers are going to have to back off.",
                "That's going to cost somebody a time — yellows out.",
                "Yellow! Someone's out of position, laps deleted likely.",
                "Frustrating yellows — someone's hot lap in the bin.",
                "Yellow flag in sector {flag} — abort, abort.",
            ],
            "flag_red": [
                "Red flag! Session stopped — will they get another run?",
                "Red flag — this could be costly for those still on the lap.",
                "That's a red. Bad news for anyone mid-flyer.",
                "Red flag! Clock frozen — what happens now?",
                "Session halted — there may not be enough time for another attempt.",
                "Red flag with the clock ticking — nerves will be shredded.",
            ],
            "accident_suspected": [
                "{driver}'s crashed! That's his qualifying done.",
                "Huge — {driver} into the wall on his lap.",
                "{driver} loses it, and that's going to bring the yellows out.",
                "{driver}'s session ends in the barriers.",
                "Oh, {driver} — he's thrown it away.",
                "Massive moment for {driver} — straight into the barrier.",
                "{driver} off on the final attempt. Heartbreak.",
                "Into the wall and it's over for {driver}.",
                "Too much, too fast — {driver} finds the barriers.",
            ],
            "battle": [
                "{chaser_driver} catching {leader_driver} — and he's on a hot lap.",
                "Traffic drama — {chaser_driver} closing fast on {leader_driver}.",
                "{leader_driver}'s on the cool-down, {chaser_driver} wants past.",
                "Compromised lap for {chaser_driver} — stuck behind {leader_driver}.",
                "{chaser_driver} has to back out of it — {leader_driver} in the way.",
                "That'll ruin {chaser_driver}'s time — {leader_driver} right ahead on a slow lap.",
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
                "Ultrapassagem perfeita de {driver}, P{to_pos}.",
                "Nao havia outra hipotese — {driver} la foi, P{to_pos}.",
                "{driver} aproveitou o DRS e foi de vez. P{to_pos}.",
                "Esse foi rapido — {driver} em P{to_pos} num abrir e fechar de olhos.",
                "Ataque pela exterior, bastante ousado — {driver}, P{to_pos}.",
                "Abriu uma fresta e {driver} entrou. P{to_pos}.",
                "Com toda a confianca, {driver} fecha em P{to_pos}.",
                "Que travagem! {driver} passa para P{to_pos}.",
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
                "Decisao tomada — {driver} dentro.",
                "Os pneus ja nao aguentavam mais. {driver} nas boxes.",
                "A janela esta aberta — {driver} entra agora.",
                "Undercut ou overcut? {driver} entra para responder a essa questao.",
                "Pit lane para {driver}. A equipa vai ter que trabalhar rapido.",
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
                "{driver} dispara para fora das boxes.",
                "Pneus novos, nova oportunidade — {driver}.",
                "La sai {driver}, vamos ver onde caiu na pista.",
                "O cronometro dira se o undercut resultou — {driver} esta fora.",
                "Excelente paragem — {driver} em pista.",
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
                "Todos os sectores roxos — {driver}, {time}. Sensacional.",
                "Nova volta mais rapida! {driver} destrói o benchmark com {time}.",
                "Ele esta a voar — {driver}, {time}.",
                "Essa volta esta noutro campeonato. {driver}, {time}.",
                "{driver} no limite toda a volta — {time}.",
            ],
            "lead_change": [
                "Temos novo lider! {new_driver} passa {old_driver}!",
                "Conseguiu — {new_driver} na lideranca!",
                "A ultrapassagem pela vitoria — {new_driver} a frente.",
                "Adeus {old_driver}, ola {new_driver}.",
                "{new_driver} destrona {old_driver}!",
                "Em P1 — {new_driver}. Grande momento.",
                "Troca no topo! {new_driver} lidera.",
                "{new_driver} capitaliza e lidera o pelotao!",
                "Mudanca sismica na frente — {new_driver} esta na lideranca.",
                "{old_driver} perde a lideranca — {new_driver} ataca e consegue.",
                "Extraordinario — {new_driver} toma o controlo desta corrida.",
                "A lideranca muda de maos! {new_driver} na frente.",
            ],
            "flag_green": [
                "Bandeira verde — e la vamos nos outra vez.",
                "Pista livre, a correr.",
                "Verde outra vez — vamos la.",
                "Tudo limpo agora, a pleno gas.",
                "Os comissarios limparam — verde, a correr!",
                "Corrida retomada — bandeira verde!",
                "Tudo resolvido — verde e a pisar!",
                "Corrida a pleno ritmo novamente.",
            ],
            "flag_yellow": [
                "Amarelas — atencao, pilotos.",
                "Dupla amarela — algo aconteceu.",
                "Cuidado, amarela no sector.",
                "Amarela no ar — aliviar a carga.",
                "Bandeira amarela — alguem teve um susto.",
                "Amarela a acenar — sem ultrapassagens.",
                "Algo se passou — amarela no sector.",
                "Reduzir a velocidade — amarela.",
            ],
            "flag_red": [
                "Bandeira vermelha. Sessao parada.",
                "E vermelha — regresso as boxes.",
                "Vermelha. Coisa seria.",
                "Tudo parado — vermelha.",
                "Vermelha! Todos a abrandar.",
                "Sessao suspensa — bandeira vermelha.",
                "Paragem total — aconteceu algo significativo.",
            ],
            "flag_blue": [
                "Azuis — tem que dar passagem.",
                "Azul, lideres a chegar.",
                "Trafego — azul para o retardatario.",
                "Bandeira azul — deixa passar!",
                "Retardatarios — azul a acenar.",
                "Passagem obrigatoria — bandeira azul.",
            ],
            "flag_white": [
                "Branca — carro lento a frente.",
                "Cuidado, branca, alguem a rastejar.",
                "Bandeira branca — veiculo lento em pista.",
                "Atencao na pista — bandeira branca.",
            ],
            "flag_checkered": [
                "E cai a xadrezada!",
                "Ai esta — bandeira de xadrez!",
                "Cruza a meta — xadrezada!",
                "A bandeira quadriculada esta no ar — corrida terminada!",
                "Fim de corrida — bandeira quadriculada!",
            ],
            "flag_generic": [
                "Mudanca de bandeira — {flag}.",
                "{flag} no ar. Atencao.",
                "Bandeira {flag} apresentada.",
                "Posto de marshalls — {flag}.",
            ],
            "race_start": [
                "Luzes apagadas, e la vao eles!",
                "E luzes apagadas — estao a correr!",
                "La vao eles, la vao eles!",
                "Cinco luzes vermelhas — apagam-se — temos corrida!",
                "La vao eles, para a curva um.",
                "Arranque limpo e corrida em andamento.",
                "Os mostradores estao levantados — e la foram eles!",
                "Dia de corrida começa — luzes apagadas!",
                "Para a primeira travagem — completamente acelerados!",
                "Que arranque — todos parece que saiu limpo.",
                "Arranque limpo — agora e estrategia e ritmo.",
            ],
            "battle": [
                "Roda com roda por P{position} — {leader_driver} a aguentar {chaser_driver}, {gap} segundos.",
                "Luta renhida — {chaser_driver} colado a {leader_driver}.",
                "So {gap} segundos entre {leader_driver} e {chaser_driver} em P{position}.",
                "Pressao em cima de {leader_driver} — {chaser_driver} ali mesmo.",
                "A diferenca cai. {gap} segundos, P{position}.",
                "{chaser_driver} no DRS de {leader_driver}.",
                "Bela luta a brotar por P{position}.",
                "Nariz contra cauda — {chaser_driver} esta em cima de {leader_driver}.",
                "Que corrida fantástica — {leader_driver} e {chaser_driver}, P{position}.",
                "{chaser_driver} esta a fechar — consegue passar {leader_driver}?",
                "Em cada travagem, {chaser_driver} esta a tentar. P{position}.",
                "A diferenca e {gap} — e esta a diminuir.",
                "Meio segundo, P{position}. Que espetaculo.",
                "{leader_driver} a defender na perfeicao mas {chaser_driver} nao desiste.",
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
                "Oh, grande contacto! {driver} atirado para fora.",
                "Ele foi. {driver} — e uma desistencia.",
                "Subviragem para a gravilha — {driver} encalhado.",
                "Danos na asa da frente para {driver} — acabou.",
                "{driver} perde o traseiro e nao ha nada a fazer.",
                "Que momento dramático — {driver} contra as protecoes.",
            ],
            "laps_to_go": [
                "{laps} voltas — chega a hora da verdade.",
                "Reta final — {laps} voltas.",
                "{laps} voltas a espera. Estrategia contra ritmo.",
                "Restam {laps}. Tensao a subir.",
                "{laps} para andar, a coisa aquece.",
                "{laps} voltas no quadro. O tempo foge.",
                "So {laps} voltas — qualquer coisa pode acontecer.",
                "{laps} para o fim — corrida longe de acabada.",
                "Contagem decrescente: {laps} voltas. Cada posicao conta.",
                "Estamos nas ultimas {laps} — agarro-me ao assento.",
            ],
            "checkered": [
                "E cai a xadrezada!",
                "Cruza a meta — corrida terminada!",
                "Xadrezada — que corrida!",
                "Brilhante — cruza a meta para a vitoria!",
                "A bandeira esta la fora — que atuacao!",
            ],
        },
        "practice": {
            "overtake": [
                "{driver} passa um mais lento — ar limpo agora.",
                "Trafego resolvido para {driver}, P{to_pos}.",
                "{driver} finalmente com pista livre, sobe a P{to_pos}.",
                "So gestao de trafego — {driver}, P{to_pos}.",
                "{driver} encontra um espaco e tem o ar limpo que procurava.",
                "Isso ajuda — {driver} pelo trafego, P{to_pos}.",
                "A ganhar posicao para a volta rapida — {driver}, P{to_pos}.",
                "{driver} trata do trafego, agora pode fazer a sua volta.",
            ],
            "pit_entry": [
                "{driver} volta as boxes — vao ver a telemetria.",
                "La entra {driver}, acerto de setup provavelmente.",
                "Fim de run para {driver} — regressa a garagem.",
                "{driver} nas boxes, engenheiros vao querer conversa.",
                "{driver} entra — possivelmente mudanca de setup.",
                "Run terminado para {driver} — de volta a box.",
                "Engenheiros a chamar {driver} para verificar o equilibrio.",
                "{driver} chama-o cedo, quer uma conversa de setup.",
                "Final da corrida longa — {driver} de volta dentro.",
                "A entrar para avaliar o desgaste de pneus. {driver} dentro.",
            ],
            "pit_exit": [
                "{driver} de volta a pista — novo plano.",
                "{driver} sai outra vez, mais voltas ai vem.",
                "{driver} sai da garagem, a rolar.",
                "Pneus novos para {driver}, vamos ver o ritmo.",
                "{driver} regressa com setup ajustado — interessante.",
                "De volta a borracha, {driver}. Vamos ver a melhoria.",
                "Agora na simulacao de quali — {driver}.",
                "Pneus novos, dados novos — {driver} la fora.",
                "{driver} volta. Engenheiros vao observar de perto.",
            ],
            "fastest_lap": [
                "Boa referencia para {driver} — {time}.",
                "{driver} lidera os tempos, {time}. Ainda ha mais.",
                "Bom tempo de referencia — {driver}, {time}.",
                "{driver} mostra o ritmo: {time}.",
                "Volta arrumada de {driver} — {time} no quadro.",
                "Nao e uma volta de quali, mas ainda assim — {driver}, {time}.",
                "Sector medio solido foi a chave — {driver}, {time}.",
                "{driver} em borracha nova — {time}. Digno de nota.",
                "P1 no treino — {driver}, {time}. Nao tirar conclusoes precipitadas.",
                "O mais rapido ate agora. {driver}, {time}.",
            ],
            "flag_green": [
                "Verde na saida das boxes — sessao ao vivo.",
                "Estamos em verde. Carros a sair.",
                "Pit lane aberta, treino comecou.",
                "Sessao comeca — pneus precisam de aquecer, devagar ao inicio.",
                "Bandeira verde, e {driver} e o primeiro a sair.",
            ],
            "flag_yellow": [
                "Amarela no sector — alguem teve um problema.",
                "Amarelas no ar. Alguem se assustou.",
                "Bandeira amarela — alguem foi para fora. Hora de investigar.",
                "Amarela a acenar — sessao pode ficar um pouco complicada.",
            ],
            "flag_red": [
                "Vermelha — sessao interrompida.",
                "Sera vermelha. De regresso as boxes.",
                "Vermelha no treino — perda de tempo de rodagem importante.",
                "Isso parou a sessao. Bandeira vermelha.",
            ],
            "accident_suspected": [
                "{driver} parou em pista — pode ser caixa ou algo assim.",
                "Parece problema para {driver}, tirou-se da linha.",
                "{driver} imobilizado — possivelmente so precaucao.",
                "{driver} no escape — pequeno momento, sem drama.",
                "{driver} esta parado — vamos aguardar noticias da garagem.",
                "Possivelmente falha mecanica para {driver} — ele parou.",
                "Pequeno escorregao de {driver} — para a relva, mas esta bem.",
                "{driver} teve um momento — saiu na saida, voltou.",
            ],
            "battle": [
                "{chaser_driver} numa volta rapida atras de {leader_driver} — trafego.",
                "Complicado — {chaser_driver} apanha {leader_driver} em push lap.",
                "Situacao de trafego — {chaser_driver} a perder tempo atras de {leader_driver}.",
                "Isso vai custar alguns decimos a {chaser_driver} — preso atras de {leader_driver}.",
                "{leader_driver} na volta de saida, {chaser_driver} na quente. Nao e ideal.",
            ],
        },
        "qualifying": {
            "overtake": [
                "{driver} passa o trafego, sobe a P{to_pos} nos tempos.",
                "P{to_pos} provisorio para {driver} — tempo registado.",
                "Tempos a mudar — {driver}, P{to_pos}.",
                "{driver} salta para P{to_pos} com essa volta.",
                "Isso chega para P{to_pos} — {driver} melhora.",
                "{driver} vai mais rapido! Provisoriamente P{to_pos}.",
                "P{to_pos} para {driver} nos ecras de cronometragem.",
                "La sobe — {driver}, P{to_pos}. A pressao esta nos outros.",
                "Sectores pessoais somam P{to_pos} para {driver}.",
            ],
            "pit_entry": [
                "{driver} de volta — primeira tentativa no bolso.",
                "{driver} desvia, rotacao rapida a caminho.",
                "La entra {driver}, set de macios a seguir.",
                "{driver} encerra o run — poupar o pneu.",
                "{driver} entra — aquela e a volta de referencia feita.",
                "A poupar borracha para a tentativa final — {driver} dentro.",
                "{driver} direto para a garagem. Borracha nova iminente.",
                "De volta debaixo das coberturas — {driver} nao gostou da volta.",
                "A proteger o pneu para mais uma tentativa — {driver} dentro.",
            ],
            "pit_exit": [
                "{driver} para a volta decisiva — e esta.",
                "La vai {driver}, ultima tentativa.",
                "{driver} de volta a pista — ultima chance pela pole.",
                "Pneus novos, ar limpo — {driver} la vai.",
                "{driver} empurra para fora das boxes. Tudo ou nada.",
                "O run final — {driver} lanca.",
                "Esta e a ultima volta de push — {driver}.",
                "La esta a luz verde — {driver}, vai!",
                "Macios novos, pista limpa — {driver} em movimento.",
                "La sai — {driver} vai querer roxo nos tres sectores.",
            ],
            "fastest_lap": [
                "Pole provisoria! {driver} — {time}!",
                "{driver} passa para o topo — {time}. Que volta.",
                "Roxo em todo o lado — {driver}, {time}!",
                "Volta seria, essa — {driver}, {time}.",
                "{driver} responde quando e preciso — {time}.",
                "Isso vai ser dificil de bater! {driver}, {time}.",
                "Levantou o nivel — {driver}, {time}.",
                "Oh, que volta! {driver} — {time}!",
                "Quase perfeita — {driver}, {time}. Pole provisoria.",
                "Sector final devastador — {driver}, {time}.",
                "{driver} encontra a volta quando mais importa — {time}.",
            ],
            "flag_green": [
                "Sessao ao vivo — saem para a pista.",
                "Pit lane em verde, qualificacao a decorrer.",
                "Vamos la — tempo no cronometro.",
                "Qualificacao comeca — quem e o primeiro a sair?",
                "Bandeira verde — o relogio esta a correr.",
                "La saem — cada decimo conta agora.",
            ],
            "flag_yellow": [
                "Amarelas — e a volta de alguem vai por agua abaixo.",
                "Amarela — vao ter que levantar o pe.",
                "Isto vai custar o tempo a alguem — amarelas.",
                "Amarela! Alguem esta fora de posicao, voltas apagadas provavelmente.",
                "Amarelas frustrantes — volta rapida de alguem no lixo.",
            ],
            "flag_red": [
                "Bandeira vermelha! Tera alguem outra tentativa?",
                "Vermelha — pode ser caro para quem estava a fazer volta.",
                "Esta e vermelha. Ma noticia a meio do flyer.",
                "Vermelha! Relogio parado — o que acontece agora?",
                "Sessao interrompida — pode nao haver tempo suficiente para outra tentativa.",
            ],
            "accident_suspected": [
                "{driver} bateu! Qualificacao acabada para ele.",
                "Enorme — {driver} contra o muro durante a volta.",
                "{driver} perde-o e vai trazer as amarelas.",
                "Sessao de {driver} termina nas barreiras.",
                "Momento enorme para {driver} — direto contra a barreira.",
                "{driver} fora na ultima tentativa. Desgosto.",
                "Contra o muro e acabou para {driver}.",
                "Demasiado, demasiado rapido — {driver} encontra as barreiras.",
            ],
            "battle": [
                "{chaser_driver} apanha {leader_driver} — em volta lancada.",
                "Drama de trafego — {chaser_driver} fecha rapido sobre {leader_driver}.",
                "Volta comprometida para {chaser_driver} — preso atras de {leader_driver}.",
                "{chaser_driver} tem que abortar — {leader_driver} no caminho.",
                "Isso vai arruinar o tempo de {chaser_driver} — {leader_driver} mesmo a frente.",
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
                "Adelantamiento perfecto de {driver}, P{to_pos}.",
                "No habia otra opcion — {driver} fue a por ello, P{to_pos}.",
                "{driver} aprovecho el DRS y punto. P{to_pos}.",
                "Eso fue rapido — {driver} en P{to_pos} en un abrir y cerrar de ojos.",
                "Ataque por fuera, muy atrevido — {driver}, P{to_pos}.",
                "Se abrio una rendija y {driver} entro. P{to_pos}.",
                "Con toda la confianza, {driver} cierra en P{to_pos}.",
                "Que frenada! {driver} pasa a P{to_pos}.",
            ],
            "pit_entry": [
                "Y aqui llega {driver} — box, box.",
                "{driver} ya ha tenido bastante con esos neumaticos.",
                "{driver} se desvia al pit lane.",
                "Entrada a boxes para {driver} — quiza undercut.",
                "Ahi va {driver} a pit lane, gran apuesta.",
                "Estrategia — {driver} a boxes.",
                "Parada para {driver}, renuncia a la posicion.",
                "{driver} a entrar — a ver que neumatico ponen.",
                "Decision tomada — {driver} adentro.",
                "Los neumaticos ya no aguantaban mas. {driver} a boxes.",
                "La ventana esta abierta — {driver} entra ahora.",
                "Undercut o overcut? {driver} entra para responder esa pregunta.",
                "Pit lane para {driver}. El equipo tendra que trabajar rapido.",
            ],
            "pit_exit": [
                "Y {driver} esta de vuelta, gomas nuevas.",
                "Sale {driver}, todo limpio por lo que parece.",
                "{driver} reincorporado — veamos en que puesto.",
                "Ruedas puestas — {driver} a por ellos.",
                "A tope {driver} saliendo del pit lane.",
                "{driver} de vuelta a la pelea, gomas frescas.",
                "Parada hecha, {driver} sigue adelante.",
                "{driver} sale disparado de boxes.",
                "Gomas nuevas, nueva oportunidad — {driver}.",
                "Sale {driver}, veamos donde ha quedado en pista.",
                "El cronometro dira si el undercut funciono — {driver} esta fuera.",
                "Excelente parada — {driver} en pista.",
            ],
            "fastest_lap": [
                "Uy, morado por todos lados — {driver}, {time}!",
                "Vuelta rapida, {driver} en {time}. Que bueno.",
                "{driver} enciende los cronos — {time}.",
                "Referencia nueva, {driver}, {time}.",
                "Pero de donde ha salido esto? {driver}, {time}.",
                "Un {time} para {driver}. Esta encontrando tiempo.",
                "Morado, morado, morado — {driver}, {time}.",
                "Todos los sectores en morado — {driver}, {time}. Sensacional.",
                "Nueva vuelta rapida! {driver} destroza el benchmark con {time}.",
                "Esta volando — {driver}, {time}.",
                "Esa vuelta esta en otro campeonato. {driver}, {time}.",
                "{driver} al limite durante toda la vuelta — {time}.",
            ],
            "lead_change": [
                "Tenemos nuevo lider! {new_driver} supera a {old_driver}!",
                "Lo ha hecho — {new_driver} en cabeza!",
                "El adelantamiento por la victoria — {new_driver} al frente.",
                "Adios {old_driver}, hola {new_driver}.",
                "{new_driver} destrona a {old_driver}!",
                "En P1 — {new_driver}. Gran momento.",
                "Cambio al frente! {new_driver} lidera.",
                "{new_driver} capitaliza y lidera el pelotón!",
                "Cambio sismico en cabeza — {new_driver} esta en la liderazgo.",
                "{old_driver} pierde el liderato — {new_driver} aprovecha.",
                "Extraordinario — {new_driver} toma el control de esta carrera.",
                "El liderato cambia de manos. {new_driver} al frente.",
            ],
            "flag_green": [
                "Verde — y alla vamos de nuevo.",
                "Pista libre, a correr.",
                "Verde otra vez — vamos alla.",
                "Todo limpio, a tope.",
                "Los comisarios han limpiado — verde, a correr!",
                "Carrera reanudada — bandera verde!",
                "Todo resuelto — verde y a pisar!",
                "Carrera a pleno ritmo de nuevo.",
            ],
            "flag_yellow": [
                "Amarillas — atentos, pilotos.",
                "Doble amarilla — algo ha pasado.",
                "Cuidado, amarilla en sector.",
                "Amarilla — levantar el pie.",
                "Bandera amarilla — alguien ha tenido un susto.",
                "Amarilla agitandose — sin adelantamientos.",
                "Algo ha pasado — amarilla en el sector.",
                "Reducir velocidad — amarilla.",
            ],
            "flag_red": [
                "Bandera roja. Sesion detenida.",
                "Es roja — de vuelta a boxes.",
                "Roja. Algo serio.",
                "Todo parado — roja.",
                "Roja! Todo el mundo a frenar.",
                "Sesion suspendida — bandera roja.",
                "Parada total — ha pasado algo importante.",
            ],
            "flag_blue": [
                "Azules — tiene que dejar pasar.",
                "Azul, lideres llegando.",
                "Trafico — azul para el rezagado.",
                "Bandera azul — deja pasar!",
                "Rezagados — azul agitandose.",
                "Paso obligatorio — bandera azul.",
            ],
            "flag_white": [
                "Blanca — coche lento delante.",
                "Cuidado, blanca, alguien arrastrandose.",
                "Bandera blanca — vehiculo lento en pista.",
                "Atentos en pista — bandera blanca.",
            ],
            "flag_checkered": [
                "Y cae la bandera a cuadros!",
                "Ahi esta — bandera de cuadros!",
                "Cruza la meta — cuadros!",
                "La bandera a cuadros ondea — se acabo!",
                "Fin de carrera — la bandera a cuadros esta fuera!",
            ],
            "flag_generic": [
                "Cambio de bandera — {flag}.",
                "{flag} al aire. Atentos.",
                "Bandera {flag} presentada.",
                "Puesto de comisarios — {flag}.",
            ],
            "race_start": [
                "Se apagan las luces, y alla van!",
                "Luces fuera — arranca la carrera!",
                "Alla van, alla van!",
                "Cinco rojas — se apagan — carrera en marcha!",
                "A por la curva uno!",
                "Salida limpia y carrera en marcha.",
                "Los paneles estan levantados — y alla fueron!",
                "El dia de carrera comienza — luces apagadas!",
                "Hacia la primera frenada — a tope!",
                "Vaya salida — todos parecen haber arrancado limpio.",
                "Salida limpia — ahora es cuestion de estrategia y ritmo.",
            ],
            "battle": [
                "Rueda con rueda por P{position} — {leader_driver} aguantando a {chaser_driver}, {gap} segundos.",
                "Buena pelea — {chaser_driver} pegado a {leader_driver}.",
                "Solo {gap} segundos entre {leader_driver} y {chaser_driver} por P{position}.",
                "Presion para {leader_driver} — {chaser_driver} ahi mismo.",
                "La diferencia baja. {gap} segundos, P{position}.",
                "{chaser_driver} en DRS de {leader_driver}.",
                "Duelo interesante por P{position}.",
                "Morro a cola — {chaser_driver} esta encima de {leader_driver}.",
                "Que carrera fantastica — {leader_driver} y {chaser_driver}, P{position}.",
                "{chaser_driver} esta cerrando — puede pasar a {leader_driver}?",
                "En cada frenada, {chaser_driver} lo intenta. P{position}.",
                "La diferencia es {gap} — y se esta reduciendo.",
                "Medio segundo, P{position}. Que espectaculo.",
                "{leader_driver} defendiendo de lujo pero {chaser_driver} no se rinde.",
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
                "Oh, gran contacto! {driver} golpeado.",
                "Se ha ido. {driver} — es un abandono.",
                "Subvirada hacia la grava — {driver} encallado.",
                "Danos en el alerón delantero para {driver} — ha acabado.",
                "{driver} pierde el trasero y no puede hacer nada.",
                "Que momento dramatico — {driver} contra las protecciones.",
            ],
            "laps_to_go": [
                "{laps} vueltas — llega la hora de la verdad.",
                "Recta final — {laps} vueltas.",
                "{laps} vueltas por delante. Estrategia contra ritmo.",
                "Quedan {laps}. Tension maxima.",
                "{laps} por rodar, la cosa se pone caliente.",
                "{laps} en el panel. El tiempo se acaba.",
                "Solo {laps} vueltas — cualquier cosa puede pasar.",
                "{laps} para el final — la carrera lejos de acabarse.",
                "Cuenta atras: {laps} vueltas. Cada posicion importa.",
                "Estamos en las ultimas {laps} — agarrense.",
            ],
            "checkered": [
                "Y cae la bandera a cuadros!",
                "Cruza la meta — fin de carrera!",
                "Cuadros — que carrera!",
                "Brillante — cruza la meta para llevarse la victoria!",
                "La bandera esta fuera — que actuacion!",
            ],
        },
        "practice": {
            "overtake": [
                "{driver} pasa a uno mas lento — aire limpio ahora.",
                "Trafico resuelto para {driver}, P{to_pos}.",
                "{driver} por fin con pista libre, P{to_pos}.",
                "Solo gestion de trafico — {driver}, P{to_pos}.",
                "{driver} encuentra un hueco y tiene el aire limpio que buscaba.",
                "Eso ayuda — {driver} por el trafico, P{to_pos}.",
                "Ganando posicion para la vuelta rapida — {driver}, P{to_pos}.",
                "{driver} gestiona el trafico, ahora puede hacer su vuelta.",
            ],
            "pit_entry": [
                "{driver} vuelve al box — a revisar datos.",
                "Ahi entra {driver}, cambio de setup probablemente.",
                "{driver} termina el run — vuelve al garaje.",
                "{driver} a boxes, ingenieros querran hablar.",
                "{driver} entra — posiblemente cambio de setup.",
                "Run terminado para {driver} — de vuelta a boxes.",
                "Ingenieros llamando a {driver} para revisar el equilibrio.",
                "{driver} entra pronto, quiere hablar de setup.",
                "Final de la tanda larga — {driver} adentro.",
                "Entrando para evaluar el desgaste. {driver} dentro.",
            ],
            "pit_exit": [
                "{driver} de vuelta a pista — nuevo plan.",
                "{driver} sale otra vez, mas vueltas por delante.",
                "{driver} sale del garaje, rodando.",
                "Neumaticos nuevos para {driver}, veamos el ritmo.",
                "{driver} regresa con setup ajustado — interesante.",
                "De vuelta a la goma, {driver}. Veamos la mejora.",
                "Ahora en la simulacion de clasi — {driver}.",
                "Gomas nuevas, datos nuevos — {driver} fuera.",
                "{driver} vuelve. Los ingenieros observaran de cerca.",
            ],
            "fastest_lap": [
                "Buena referencia de {driver} — {time}.",
                "{driver} lidera los tiempos, {time}. Aun queda mas.",
                "Buen tiempo de referencia — {driver}, {time}.",
                "{driver} muestra el ritmo: {time}.",
                "Vuelta ordenada de {driver} — {time} en el tablero.",
                "No es una vuelta de clasi, pero aun asi — {driver}, {time}.",
                "Sector medio solido fue la clave — {driver}, {time}.",
                "{driver} en goma nueva — {time}. A tener en cuenta.",
                "P1 en entrenos — {driver}, {time}. No sacar conclusiones precipitadas.",
                "El mas rapido hasta ahora. {driver}, {time}.",
            ],
            "flag_green": [
                "Verde a la salida del pit lane — sesion en marcha.",
                "Estamos en verde. Coches saliendo.",
                "Pit lane abierto, entrenamiento en marcha.",
                "Sesion comienza — los neumaticos necesitan calentar, despacio al inicio.",
                "Bandera verde, y {driver} es el primero en salir.",
            ],
            "flag_yellow": [
                "Amarilla en sector — alguien ha tenido un problema.",
                "Amarillas al aire. Alguien se ha asustado.",
                "Bandera amarilla — alguien se ha ido. Hora de investigar.",
                "Amarilla agitandose — la sesion puede complicarse.",
            ],
            "flag_red": [
                "Roja — sesion interrumpida.",
                "Sera roja. De vuelta a boxes.",
                "Roja en entrenos — tiempo de rodaje perdido.",
                "Eso ha parado la sesion. Bandera roja.",
            ],
            "accident_suspected": [
                "{driver} parado en pista — puede ser caja o similar.",
                "Parece problema para {driver}, fuera de la linea.",
                "{driver} detenido — probablemente precaucion.",
                "{driver} en el escape — momento pequeno, sin drama.",
                "{driver} esta parado — esperaremos noticias del garaje.",
                "Posible fallo mecanico para {driver} — se ha parado.",
                "Pequeno deslizamiento de {driver} — a la hierba, pero bien.",
                "{driver} ha tenido un momento — salio en la salida, volvio.",
            ],
            "battle": [
                "{chaser_driver} en vuelta rapida tras {leader_driver} — trafico.",
                "Lio — {chaser_driver} pilla a {leader_driver} en push lap.",
                "Situacion de trafico — {chaser_driver} perdiendo tiempo detras de {leader_driver}.",
                "Eso costara decimas a {chaser_driver} — atascado detras de {leader_driver}.",
                "{leader_driver} en vuelta de calentamiento, {chaser_driver} a tope. No es ideal.",
            ],
        },
        "qualifying": {
            "overtake": [
                "{driver} pasa el trafico, sube a P{to_pos} en los tiempos.",
                "P{to_pos} provisional para {driver} — tiempo registrado.",
                "Tiempos cambiando — {driver}, P{to_pos}.",
                "{driver} salta a P{to_pos} con esa vuelta.",
                "Eso es suficiente para P{to_pos} — {driver} mejora.",
                "{driver} va mas rapido! Provisionalmente P{to_pos}.",
                "P{to_pos} para {driver} en los pantallas de cronometraje.",
                "Arriba — {driver}, P{to_pos}. La presion esta en los demas.",
                "Sectores personales suman P{to_pos} para {driver}.",
            ],
            "pit_entry": [
                "{driver} de vuelta — primer intento guardado.",
                "{driver} se desvia, rotacion rapida.",
                "Ahi entra {driver}, set de blandos a continuacion.",
                "{driver} cierra el run — cuidar el neumatico.",
                "{driver} entra — esa es la vuelta de referencia hecha.",
                "Guardando goma para el intento final — {driver} dentro.",
                "{driver} directo al garaje. Goma nueva inminente.",
                "De vuelta bajo las fundas — {driver} no esta contento con esa vuelta.",
                "Protegiendo la goma para un ultimo intento — {driver} dentro.",
            ],
            "pit_exit": [
                "{driver} para la vuelta decisiva — esta es.",
                "Ahi va {driver}, ultimo intento.",
                "{driver} de vuelta — ultima oportunidad por la pole.",
                "Neumaticos nuevos, aire limpio — {driver} se lanza.",
                "{driver} empuja fuera de boxes. Todo o nada.",
                "El run final — {driver} se lanza.",
                "Este es el ultimo push lap — {driver}.",
                "Ahi esta la luz verde — {driver}, ve!",
                "Blandos nuevos, pista libre — {driver} en movimiento.",
                "Sale — {driver} querrapurpura en los tres sectores.",
            ],
            "fastest_lap": [
                "Pole provisional! {driver} — {time}!",
                "{driver} pasa arriba — {time}. Vuelton.",
                "Morado por todos lados — {driver}, {time}!",
                "Vuelta seria, esa — {driver}, {time}.",
                "{driver} responde cuando toca — {time}.",
                "Eso va a ser dificil de batir! {driver}, {time}.",
                "Ha subido el liston — {driver}, {time}.",
                "Oh, que vuelta! {driver} — {time}!",
                "Casi perfecta — {driver}, {time}. Pole provisional.",
                "Sector final demoledor — {driver}, {time}.",
                "{driver} encuentra la vuelta cuando mas importa — {time}.",
            ],
            "flag_green": [
                "Sesion en marcha — salen a pista.",
                "Pit lane en verde, clasificacion en marcha.",
                "Vamos — tiempos al cronometro.",
                "Clasificacion comienza — quien es el primero en salir?",
                "Bandera verde — el reloj esta corriendo.",
                "Ahi salen — cada decima cuenta ahora.",
            ],
            "flag_yellow": [
                "Amarillas — la vuelta de alguien se va al traste.",
                "Amarilla — tendran que levantar.",
                "Esto le va a costar a alguien — amarillas.",
                "Amarilla! Alguien esta fuera de posicion, vueltas borradas probablemente.",
                "Amarillas frustrantes — la vuelta rapida de alguien a la basura.",
            ],
            "flag_red": [
                "Roja! Tendra alguien otra oportunidad?",
                "Roja — puede ser caro para quien estuviera en vuelta.",
                "Esta es roja. Mala noticia a mitad de flyer.",
                "Roja! Reloj parado — que pasa ahora?",
                "Sesion interrumpida — puede no haber tiempo para otro intento.",
            ],
            "accident_suspected": [
                "{driver} se ha estrellado! Clasi acabada para el.",
                "Enorme — {driver} contra el muro en su vuelta.",
                "{driver} lo pierde, y traera las amarillas.",
                "Sesion de {driver} termina en las barreras.",
                "Gran momento para {driver} — directo contra la barrera.",
                "{driver} fuera en el ultimo intento. Que pena.",
                "Contra el muro y se acabo para {driver}.",
                "Demasiado, demasiado rapido — {driver} encuentra las barreras.",
            ],
            "battle": [
                "{chaser_driver} pilla a {leader_driver} — en vuelta lanzada.",
                "Drama de trafico — {chaser_driver} cerrando sobre {leader_driver}.",
                "Vuelta comprometida para {chaser_driver} — atascado detras de {leader_driver}.",
                "{chaser_driver} tiene que abortar — {leader_driver} en el camino.",
                "Eso arruinara el tiempo de {chaser_driver} — {leader_driver} justo delante.",
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
                "完璧なブレーキングで{driver}、P{to_pos}。",
                "コミットメント！{driver}、隙間を見つけてP{to_pos}。",
                "躊躇なし — {driver}が一気に抜いてP{to_pos}。",
                "今レース最高のオーバーテイクかもしれない。{driver}、P{to_pos}。",
                "クリーン、正確、容赦なし — {driver}がP{to_pos}へ。",
                "少しの隙間でも{driver}は見逃さない。P{to_pos}。",
                "{driver}、勢いを活かしてP{to_pos}へ。",
                "完全にアウトブレーキング — {driver}、P{to_pos}。",
                "これが追い上げだ。P{from_pos}からP{to_pos}、{driver}。",
                "アウトサイドから大胆な仕掛け！{driver}、P{to_pos}。",
                "開いた隙を{driver}は逃さなかった。P{to_pos}。",
            ],
            "pit_entry": [
                "さあ、{driver}がピットに入ってきます。",
                "{driver}、もうタイヤが限界のようです。",
                "ボックス、ボックス — {driver}。",
                "{driver}、戦略が動きます。ピットイン。",
                "アンダーカット狙いか、{driver}がピットへ。",
                "ポジションを捨てて、{driver}が入る。",
                "{driver}、ピットレーンへ飛び込みました。",
                "決断が下された — {driver}、フレッシュタイヤへ。",
                "タイヤはもう限界でした。{driver}に選択肢はなかった。",
                "ウィンドウが開いている — {driver}が今入る。",
                "アンダーカットかオーバーカットか？{driver}が入って答えを出す。",
                "{driver}のピットインです。クルーは素早く動かないといけない。",
            ],
            "pit_exit": [
                "{driver}、新品タイヤで戻ってきました。",
                "クリーンなストップ、{driver}復帰。",
                "{driver}がピットアウト、どこに戻れるか。",
                "タイヤを履き替えて、{driver}が再び加速。",
                "{driver}、再びバトルの中へ。",
                "素晴らしい作業、{driver}が飛び出します。",
                "作業完了、{driver}がコース復帰。",
                "{driver}がピットボックスから猛スピードで飛び出す。",
                "クルーが完璧な仕事。{driver}、行った。",
                "フレッシュタイヤ、新たな希望 — {driver}が再び戦列へ。",
                "クリアなエアへ、{driver}。そのタイヤを生かして。",
                "ストップウォッチが答えを出す — {driver}が解放された。",
            ],
            "fastest_lap": [
                "おっと、パープル続出 — {driver}、{time}！",
                "ファステストラップ、{driver}の{time}です。",
                "{driver}、タイムシートのトップへ、{time}。",
                "基準タイム更新、{driver}の{time}。",
                "どこから出したのか、{driver}の{time}。",
                "{time}を叩き出した{driver}、絶好調。",
                "全セクターパープル — {driver}、{time}。センセーショナル。",
                "新ファステストラップ！{driver}が{time}でベンチマークを粉砕。",
                "完全に飛んでいる — {driver}、{time}。",
                "この周回は別次元だ。{driver}、{time}。",
                "{driver}、最後までフルアタック — {time}。",
            ],
            "lead_change": [
                "トップが変わった！{new_driver}が{old_driver}を抜いた！",
                "やりました、{new_driver}がトップに！",
                "優勝争いでの一発 — {new_driver}が先頭。",
                "さようなら{old_driver}、{new_driver}がリード。",
                "{new_driver}、ついに{old_driver}を攻略。",
                "首位に立ったのは{new_driver}、大きな瞬間です。",
                "{new_driver}がチャンスを活かして先頭集団をリード！",
                "先頭に地殻変動 — {new_driver}がレースをリード。",
                "{old_driver}が首位を失う — {new_driver}が飛び込む。",
                "驚異的 — {new_driver}がこのレースをコントロール下に。",
                "首位が入れ替わる。{new_driver}が前に出た。",
            ],
            "flag_green": [
                "グリーンフラッグ、再びレース開始です。",
                "コースクリア、走行再開。",
                "グリーンです、肘を張って。",
                "全て解除、グリーン。",
                "スチュワードがクリアした — グリーン、行け！",
                "レース再開 — グリーンフラッグ！",
                "全て解決 — グリーンでフル加速！",
                "再びフルレーシングコンディション。",
            ],
            "flag_yellow": [
                "イエロー、ドライバーは注意。",
                "ダブルイエロー — 何かが起きた。",
                "セクターにイエロー、慎重に。",
                "イエローフラッグ、ペースダウン。",
                "イエロー — マーシャルポスト、注意を。",
                "速度を落として、インシデントがあった。",
                "イエロー振られている — ここでは追い越し禁止。",
                "何かがあった — セクターにイエロー。",
            ],
            "flag_red": [
                "赤旗、セッション中断です。",
                "これは赤旗 — 全車ピットへ。",
                "赤旗、深刻な状況です。",
                "走行停止、赤旗提示。",
                "赤旗！安全に減速して整列。",
                "セッションは停止されました — 赤旗。",
                "全停止 — 何か重大なことが起きた。",
            ],
            "flag_blue": [
                "ブルーフラッグ — 譲らないと。",
                "ブルー、先頭集団が来ます。",
                "周回遅れにブルー。",
                "道を開けろ！ブルーフラッグが振られている。",
                "周回遅れ車 — ブルーフラッグ、先頭を通せ。",
                "義務的な通過 — ブルーフラッグ。",
            ],
            "flag_white": [
                "ホワイトフラッグ — 低速車あり。",
                "注意、低速車が前方に。",
                "ホワイトフラッグ提示 — コース上に低速車。",
                "前方に危険 — ホワイトフラッグ。",
            ],
            "flag_checkered": [
                "チェッカードフラッグが振られました！",
                "ゴール — チェッカー！",
                "ラインを越えて、チェッカーフラッグ！",
                "チェッカーが振られる — 終わった！",
                "レース終了 — チェッカーフラッグが出た！",
            ],
            "flag_generic": [
                "フラッグ変化 — {flag}。",
                "{flag}フラッグ提示、注意。",
                "{flag}フラッグが掲示されました。",
                "マーシャルポスト — {flag}。",
            ],
            "race_start": [
                "ライトアウト、レーススタート！",
                "シグナル消灯、スタート！",
                "さあ、行きました、行きました！",
                "5つのライトが消えた — レース開始！",
                "ターン1に向かってオープニングラップ！",
                "クリーンなスタート、レースが動き出します。",
                "ボードが上がった — そして行った！",
                "レースデイが始まる — ライトアウト！",
                "最初のブレーキングゾーンへ — フルスロットル！",
                "素晴らしいスタート — 全員クリーンに出たようだ。",
                "クリーンなスタート — あとは戦略とペースの勝負。",
            ],
            "battle": [
                "P{position}争い — {leader_driver}が{chaser_driver}を抑える、差は{gap}秒。",
                "激しい攻防、{chaser_driver}が{leader_driver}の真後ろに。",
                "わずか{gap}秒、P{position}をめぐる戦い。",
                "{leader_driver}にプレッシャー、{chaser_driver}が迫ります。",
                "差が縮まる、{gap}秒、P{position}。",
                "{chaser_driver}、DRS圏内へ。",
                "ノーズ・トゥ・テール — {chaser_driver}が{leader_driver}にピッタリ。",
                "素晴らしいレース — {leader_driver}と{chaser_driver}、P{position}。",
                "{chaser_driver}は詰めている — {leader_driver}を抜けるか？",
                "毎コーナー、{chaser_driver}がチャレンジ。P{position}。",
                "差は{gap} — そしてさらに縮まっている。",
                "0.5秒、P{position}。これは見ものだ。",
                "{leader_driver}は見事なディフェンスだが{chaser_driver}も諦めない。",
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
                "大きな接触！{driver}が弾き飛ばされた。",
                "終わった。{driver} — リタイアだ。",
                "アンダーステアでグラベルへ — {driver}が乗り上げた。",
                "フロントウィング損傷で{driver}は終わった。",
                "リアが流れて{driver}にはどうしようもなかった。",
                "ドラマチックな瞬間 — {driver}がバリアに向かって行った。",
            ],
            "laps_to_go": [
                "残り{laps}周 — いよいよ正念場。",
                "ファイナルステージ、あと{laps}周。",
                "{laps}周、戦略か純粋なペースか。",
                "残り{laps}周、緊張が高まります。",
                "あと{laps}、時間がありません。",
                "わずか{laps}周 — 何が起きてもおかしくない。",
                "{laps}周でゴール — このレースはまだ終わっていない。",
                "カウントダウン：残り{laps}周。全ポジションが重要。",
                "最後の{laps}周 — シートベルトを締めて。",
            ],
            "checkered": [
                "チェッカーを受けました！",
                "ゴール — レース終了！",
                "チェッカー、素晴らしいレースでした。",
                "見事 — ラインを越えて勝利！",
                "フラッグが出ました — 素晴らしいパフォーマンス！",
            ],
        },
        "practice": {
            "overtake": [
                "{driver}、遅いマシンをパス、クリアな空気へ。",
                "トラフィック処理、{driver}がP{to_pos}。",
                "{driver}、やっとクリアラップを取れます。",
                "順位操作ではなく、トラフィックの問題です。",
                "{driver}、隙間を見つけて求めていたクリアエアを確保。",
                "助かった — {driver}がトラフィックを抜けてP{to_pos}。",
                "ファストラップに向けてポジション確保 — {driver}、P{to_pos}。",
                "{driver}がトラフィックを処理、これで周回できる。",
            ],
            "pit_entry": [
                "{driver}、ピットイン、データ確認でしょう。",
                "セッティング変更か、{driver}がガレージへ。",
                "{driver}、ランを終えてピットへ。",
                "エンジニアと話すためでしょう、{driver}が戻ります。",
                "{driver}、入ってくる — セットアップ変更の可能性。",
                "ランが終わった{driver} — ボックスへ戻る。",
                "エンジニアが{driver}を呼んでバランスを確認。",
                "{driver}が早めに入る、セットアップの話がしたいのだろう。",
                "ロングランが終わった — {driver}が戻ってきた。",
                "タイヤ摩耗を評価するために入ってきた。{driver}、ピットイン。",
            ],
            "pit_exit": [
                "{driver}、再びコースへ — 新しいランプラン。",
                "また走り出しました、{driver}。",
                "{driver}、ガレージからロールアウト。",
                "新品タイヤで{driver}、ペースを見ましょう。",
                "{driver}、セットアップを調整して戻ってきた — 興味深い。",
                "ゴムに戻って、{driver}。改善を見よう。",
                "予選シミュレーションに入る — {driver}。",
                "新品タイヤ、新データ — {driver}アウト。",
                "{driver}が戻ってきた。エンジニアは注目している。",
            ],
            "fastest_lap": [
                "{driver}、良い基準ラップ、{time}。",
                "{driver}、タイムシートでトップ、{time}。まだ余力あり。",
                "良い参考タイム、{driver}、{time}。",
                "{driver}、ペースを示しました、{time}。",
                "{driver}のきれいなラップ — {time}がボードに。",
                "予選ラップではないが、それでも — {driver}、{time}。",
                "中間セクターが堅固だった — {driver}、{time}。",
                "{driver}、新品タイヤで — {time}。注目に値する。",
                "プラクティスで1位 — {driver}、{time}。あまり結論を急ぐな。",
                "今のところ最速。{driver}、{time}。",
            ],
            "flag_green": [
                "ピット出口グリーン、セッション開始。",
                "グリーンです、マシンが続々と出てきます。",
                "ピットレーンオープン、プラクティス開始。",
                "セッション開始 — タイヤを温める必要がある、最初はゆっくり。",
                "グリーンフラッグ、{driver}が最初に出た。",
            ],
            "flag_yellow": [
                "セクターにイエロー、誰かがトラブル。",
                "イエロー、誰かが一瞬ヒヤリ。",
                "イエローフラッグ — 誰かがコースアウト。調査が必要。",
                "イエローが振られている — セッションが少し荒れてきた。",
            ],
            "flag_red": [
                "赤旗、セッション中断。",
                "赤旗のようです、全車ピットへ。",
                "プラクティスで赤旗 — 重要な走行時間を失った。",
                "セッションが止まった。赤旗。",
            ],
            "accident_suspected": [
                "{driver}、コース上で停止 — ギアボックスかも。",
                "{driver}に問題、ラインを外れました。",
                "{driver}、停止、念のためでしょう。",
                "{driver}、ランオフに、小さな瞬間です。",
                "{driver}が止まっている — ガレージからの報告を待ちます。",
                "{driver}のメカニカルトラブルかも — 停止した。",
                "{driver}、小さなスリップ — 草の上へ、でも大丈夫。",
                "{driver}、コーナー出口でヒヤリ — 戻ってきた。",
            ],
            "battle": [
                "{chaser_driver}がプッシュラップ中、トラフィックが。",
                "{chaser_driver}、{leader_driver}に追いつきます、フライングラップ中。",
                "トラフィックの状況 — {chaser_driver}が{leader_driver}の後ろで時間を失う。",
                "これで{chaser_driver}は数テンス失う — {leader_driver}の後ろに詰まった。",
                "{leader_driver}がアウトラップ、{chaser_driver}がホットラップ。理想的ではない。",
            ],
        },
        "qualifying": {
            "overtake": [
                "{driver}、トラフィックを抜けてP{to_pos}へ浮上。",
                "暫定P{to_pos}、{driver}のタイムが入りました。",
                "タイムシート更新、{driver}がP{to_pos}。",
                "{driver}、そのラップでP{to_pos}へジャンプ。",
                "P{to_pos}で十分 — {driver}が改善。",
                "{driver}、速くなった！暫定P{to_pos}。",
                "クロノスクリーンでP{to_pos}、{driver}。",
                "上がる — {driver}、P{to_pos}。他のドライバーへプレッシャー。",
                "個人ベストセクターでP{to_pos}の{driver}。",
            ],
            "pit_entry": [
                "{driver}、ピットイン、最初のランをまとめました。",
                "{driver}、ピットへ、素早くターンアラウンド。",
                "次は新品ソフトでしょう、{driver}がピットへ。",
                "{driver}、ランを締めて、タイヤを温存。",
                "{driver}が入る — あのバンクラップはできた。",
                "最終アタックのためにタイヤを温存 — {driver}、イン。",
                "{driver}がガレージへ直行。新品タイヤが間もなく。",
                "カバーの下に戻って — そのラップに{driver}は満足していない。",
                "最後の一発のためにタイヤを守る — {driver}、イン。",
            ],
            "pit_exit": [
                "{driver}、アタックに出ます — これが本命。",
                "ラストアタック、{driver}が出ていきます。",
                "{driver}、ポールを狙うラストチャンス。",
                "新品タイヤ、クリアな空気 — {driver}、さあ。",
                "{driver}がボックスから押し出される。全か無か。",
                "最終ラン — {driver}が発進。",
                "これが最後のプッシュラップ — {driver}。",
                "グリーンライトが点灯した — {driver}、行け！",
                "新品ソフト、クリアコース — {driver}が動き出す。",
                "出た — {driver}、3セクター全てでパープルを出したい。",
            ],
            "fastest_lap": [
                "暫定ポール！{driver}、{time}！",
                "{driver}、トップタイム — {time}。素晴らしい。",
                "パープル続出、{driver}、{time}！",
                "これは本物のラップ、{driver}、{time}。",
                "{driver}、ここで仕事をします、{time}。",
                "これを上回るのは難しい！{driver}、{time}。",
                "バーを上げた — {driver}、{time}。",
                "おお、なんてラップ！{driver} — {time}！",
                "ほぼ完璧 — {driver}、{time}。暫定ポール。",
                "最終セクターで爆発 — {driver}、{time}。",
                "{driver}、大事なところで仕事をする — {time}。",
            ],
            "flag_green": [
                "セッション開始、出ていきます。",
                "ピット出口グリーン、予選スタート。",
                "さあ、タイムを刻みましょう。",
                "予選開始 — 最初に出るのは誰だ？",
                "グリーンフラッグ — クロックが動いている。",
                "出て行く — 今は1テンスごとに意味がある。",
            ],
            "flag_yellow": [
                "イエロー — 誰かのラップが台無しに。",
                "イエロー、ペースを落とさないと。",
                "これは誰かのタイムを失わせる、イエロー。",
                "イエロー！誰かがポジションを外れた、タイム抹消の可能性。",
                "悔しいイエロー — 誰かのファストラップがゴミ箱へ。",
            ],
            "flag_red": [
                "赤旗！もう一回走れるのか？",
                "赤旗、ラップ中だった人には痛い。",
                "赤旗、フライング中は大打撃。",
                "赤旗！クロック停止 — 今後どうなる？",
                "セッション中断 — もう一度アタックする時間があるかも。",
            ],
            "accident_suspected": [
                "{driver}がクラッシュ、予選終了です。",
                "大きなクラッシュ、{driver}がウォールに。",
                "{driver}、マシンを失い、イエローが出ます。",
                "{driver}のセッションがバリアで終わる。",
                "{driver}にとって大きな瞬間 — バリアへ真っ直ぐ。",
                "最後のアタックで{driver}がアウト。ハートブレイク。",
                "ウォールに当たって{driver}は終わった。",
                "速すぎた — {driver}がバリアを見つけた。",
            ],
            "battle": [
                "{chaser_driver}が{leader_driver}に接近、アタックラップ中。",
                "トラフィックドラマ、{chaser_driver}が{leader_driver}に迫ります。",
                "{chaser_driver}のラップが台無し — {leader_driver}の後ろに詰まった。",
                "{chaser_driver}はアボートしなければ — {leader_driver}が邪魔。",
                "{leader_driver}がスローラップ、{chaser_driver}のタイムを台無しにする。",
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

    def __init__(self, history_per_tag: int = 10) -> None:
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
            carnumber = data.get("car_number") or data.get("CarNumber")
            license_str = data.get("license") or data.get("LicString")

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
            if carnumber and team:
                return pick(
                    f"Car number {carnumber}, {name} representing {team}.",
                    f"Carro número {carnumber}, {name} a representar {team}.",
                    f"Coche número {carnumber}, {name} representando a {team}.",
                    f"カーナンバー{carnumber}、{team}の{name}です。",
                )
            if team:
                return pick(
                    f"{name} out there for {team} today.",
                    f"{name} em pista pela {team} hoje.",
                    f"{name} en pista con {team} hoy.",
                    f"{name}、今日は{team}で走っています。",
                )
            if irating:
                return pick(
                    f"{name} carries a {irating} iRating into this session.",
                    f"{name} entra nesta sessão com {irating} de iRating.",
                    f"{name} lleva un iRating de {irating} en esta sesion.",
                    f"{name}はこのセッションに{irating} iRatingで臨みます。",
                )
            if license_str:
                return pick(
                    f"{name} — holding a {license_str} license.",
                    f"{name} — licença {license_str}.",
                    f"{name} — licencia {license_str}.",
                    f"{name} — {license_str}ライセンス所持。",
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
        elevation = data.get("elevation_m")
        opened_year = data.get("opened_year")

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
        if elevation:
            return pick(
                f"{tname} sits at {elevation} metres above sea level — that affects aerodynamic balance.",
                f"{tname} fica a {elevation} metros acima do nível do mar — isso afeta o equilíbrio aerodinâmico.",
                f"{tname} se encuentra a {elevation} metros sobre el nivel del mar — eso afecta el equilibrio aerodinámico.",
                f"{tname}は海抜{elevation}メートル — 空力バランスに影響します。",
            )
        if opened_year:
            return pick(
                f"{tname} has been hosting racing since {opened_year}. Plenty of history here.",
                f"{tname} recebe corridas desde {opened_year}. Muita história aqui.",
                f"{tname} acoge carreras desde {opened_year}. Mucha historia aqui.",
                f"{tname}は{opened_year}年からレースを開催。多くの歴史がある。",
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
