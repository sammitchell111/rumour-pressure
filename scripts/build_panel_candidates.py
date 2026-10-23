"""Build registry/candidates.yaml: the panel for the feasibility count (PLAN.md Task 7).

Selection rule (2026-10-23):
  - binary markets on Polymarket or Kalshi with >= $10K volume;
  - about a real person's relationship or family life: pregnancy, engagement, marriage,
    divorce, breakup, dating, or wedding details/guests;
  - excluded: Taylor Swift / Travis Kelce (the flagships), reality-TV or fictional
    couples, products, legal cases, bands, parlays;
  - markets are grouped into *families* (one couple, person or event); the same question
    on two venues stays in one family; at most 5 markets per family (highest volume).

Candidates came from `rp registry find` on topic words; each entry below is
(venue, ref, family, detrend, entity keys). Run: uv run python scripts/build_panel_candidates.py
"""

from pathlib import Path

from rumour_pressure.registry import Registry, save_registry
from rumour_pressure.registry import venues as v

OUT = Path("registry/candidates.yaml")
H, N = "hazard", "none"

PANEL = [
    # politicians and business figures
    ("polymarket", "519049", "obama", H, ["Barack Obama", "Michelle Obama"]),
    ("polymarket", "974661", "clinton", H, ["Bill Clinton", "Hillary Clinton"]),
    ("polymarket", "516941", "trump-melania", H, ["Donald Trump", "Melania Trump"]),
    ("polymarket", "501939", "trump-melania", H, ["Donald Trump", "Melania Trump"]),
    ("polymarket", "2324516", "trump-son-wedding", N, ["Donald Trump", "Donald Trump Jr"]),
    ("polymarket", "519589", "harris-emhoff", H, ["Kamala Harris", "Doug Emhoff"]),
    ("polymarket", "504066", "vance", H, ["JD Vance", "Usha Vance"]),
    ("polymarket", "547378", "macron", H, ["Emmanuel Macron", "Brigitte Macron"]),
    ("polymarket", "507562", "rfk-hines", H, ["RFK Jr", "Cheryl Hines"]),
    ("polymarket", "507563", "mark-robinson", H, ["Mark Robinson"]),
    ("polymarket", "1807950", "noem", H, ["Kristi Noem"]),
    ("polymarket", "1067187", "xi", H, ["Xi Jinping", "Peng Liyuan"]),
    ("polymarket", "511467", "aoc", H, ["Alexandria Ocasio-Cortez", "AOC"]),
    ("polymarket", "561422", "bezos", H, ["Jeff Bezos", "Lauren Sanchez"]),
    ("polymarket", "519276", "zuckerberg", H, ["Mark Zuckerberg", "Priscilla Chan"]),
    ("polymarket", "908000", "musk", H, ["Elon Musk"]),
    ("polymarket", "1245165", "caroline-ellison", H, ["Caroline Ellison"]),
    ("polymarket", "567512", "roy-lee", H, ["Roy Lee", "Cluely"]),
    # entertainment
    ("polymarket", "516940", "harry-meghan", H, ["Prince Harry", "Meghan Markle"]),
    ("polymarket", "515095", "jayz-beyonce", H, ["Jay-Z", "Beyonce", "Beyoncé"]),
    ("polymarket", "516943", "jayz-beyonce", H, ["Jay-Z", "Beyonce", "Beyoncé"]),
    ("polymarket", "519349", "biebers", H, ["Justin Bieber", "Hailey Bieber"]),
    ("polymarket", "544767", "biebers", H, ["Justin Bieber", "Hailey Bieber"]),
    ("polymarket", "519734", "reynolds-lively", H, ["Ryan Reynolds", "Blake Lively"]),
    ("polymarket", "829310", "perry-trudeau", H, ["Katy Perry", "Justin Trudeau"]),
    ("kalshi", "KXENGAGEMENTTRUDEAUPERRY-26", "perry-trudeau", H, ["Katy Perry", "Justin Trudeau"]),
    ("polymarket", "1414665", "perry-trudeau", H, ["Katy Perry", "Justin Trudeau"]),
    (
        "polymarket",
        "1214584",
        "kylie-timothee",
        H,
        ["Kylie Jenner", "Timothée Chalamet", "Timothee Chalamet"],
    ),
    (
        "polymarket",
        "539249",
        "kylie-timothee",
        H,
        ["Kylie Jenner", "Timothée Chalamet", "Timothee Chalamet"],
    ),
    (
        "kalshi",
        "KXENGAGEMENTTIMOTHEEKYLIE-26",
        "kylie-timothee",
        H,
        ["Kylie Jenner", "Timothée Chalamet", "Timothee Chalamet"],
    ),
    ("polymarket", "516999", "zendaya-holland", H, ["Zendaya", "Tom Holland"]),
    ("polymarket", "1222010", "zendaya-holland", H, ["Zendaya", "Tom Holland"]),
    ("polymarket", "1006439", "zendaya-holland", H, ["Zendaya", "Tom Holland"]),
    ("polymarket", "1919236", "zendaya-holland", N, ["Zendaya", "Tom Holland"]),
    ("polymarket", "516904", "selena-gomez", H, ["Selena Gomez", "Benny Blanco"]),
    ("polymarket", "1223192", "rihanna", H, ["Rihanna", "A$AP Rocky"]),
    ("polymarket", "516905", "lana-del-rey", H, ["Lana Del Rey"]),
    ("polymarket", "506078", "lana-del-rey", H, ["Lana Del Rey"]),
    ("polymarket", "506064", "lana-del-rey", H, ["Lana Del Rey"]),
    ("polymarket", "522851", "dicaprio", H, ["Leonardo DiCaprio", "Vittoria Ceretti"]),
    ("polymarket", "1363789", "megan-klay", H, ["Megan Thee Stallion", "Klay Thompson"]),
    ("polymarket", "1363798", "megan-klay", H, ["Megan Thee Stallion", "Klay Thompson"]),
    ("kalshi", "KXENGAGEMENTMEGKLAY-26", "megan-klay", H, ["Megan Thee Stallion", "Klay Thompson"]),
    ("polymarket", "549814", "cardi-diggs", H, ["Cardi B", "Stefon Diggs"]),
    ("kalshi", "KXSTEFONDIGGSCARDIB-26", "cardi-diggs", H, ["Cardi B", "Stefon Diggs"]),
    ("polymarket", "525171", "sweeney", H, ["Sydney Sweeney"]),
    ("polymarket", "532008", "sweeney", H, ["Sydney Sweeney"]),
    ("kalshi", "KXENGAGEMENTSWEENEYBRUAN-26", "sweeney", H, ["Sydney Sweeney", "Scooter Braun"]),
    ("polymarket", "19", "kardashian-west", H, ["Kim Kardashian", "Kanye West"]),
    ("polymarket", "12017", "kardashian-west", H, ["Kim Kardashian", "Kanye West"]),
    ("polymarket", "242591", "kardashian-west", H, ["Kim Kardashian", "Pete Davidson"]),
    (
        "kalshi",
        "KXENGAGEMENTKIMLEWIS-26",
        "kardashian-hamilton",
        H,
        ["Kim Kardashian", "Lewis Hamilton"],
    ),
    ("polymarket", "522215", "ye", H, ["Ye", "Kanye West", "Bianca Censori"]),
    ("polymarket", "238905", "jlo-affleck", H, ["Jennifer Lopez", "Ben Affleck"]),
    ("polymarket", "1296018", "nara-smith", H, ["Nara Smith"]),
    ("polymarket", "523958", "tiffany-fong", H, ["Tiffany Fong"]),
    ("polymarket", "2037907", "clavicular", H, ["Clavicular"]),
    ("polymarket", "1385756", "mrbeast", H, ["MrBeast", "Thea Booysen"]),
    ("polymarket", "1428263", "larry-wheels", H, ["Larry Wheels"]),
    ("polymarket", "1361001", "aguilar-nodal", H, ["Ángela Aguilar", "Christian Nodal"]),
    ("kalshi", "KXENGAGEMENTTATEJACKHUGHES-26", "mcrae-hughes", H, ["Tate McRae", "Jack Hughes"]),
    # sport
    ("polymarket", "515500", "burrow", H, ["Joe Burrow", "Olivia Holzmacher"]),
    ("polymarket", "515818", "travis-hunter", H, ["Travis Hunter"]),
    ("polymarket", "525698", "bellingham", H, ["Jude Bellingham"]),
    ("polymarket", "4868051", "fonseca-vinicius", H, ["Virginia Fonseca", "Vinícius Júnior"]),
    (
        "kalshi",
        "KXMARRIAGEBELICHICKHUDSON-26",
        "belichick-hudson",
        H,
        ["Bill Belichick", "Jordon Hudson"],
    ),
    ("kalshi", "KXENGAGEMENTDARTBEER-26", "dart-beer", H, ["Jaxson Dart", "Madison Beer"]),
    ("kalshi", "KXENGAGEMENTPUKA-26B", "nacua-saffari", H, ["Puka Nacua", "Sara Saffari"]),
    ("kalshi", "KXENGAGEMENTTOMBRADYEARLE-26", "brady-earle", H, ["Tom Brady", "Alix Earle"]),
    # Ronaldo's wedding: top 5 guest markets by volume
    ("polymarket", "3342074", "ronaldo-wedding", N, ["Cristiano Ronaldo", "Georgina Rodriguez"]),
    ("polymarket", "3342072", "ronaldo-wedding", N, ["Cristiano Ronaldo", "Georgina Rodriguez"]),
    ("polymarket", "3342077", "ronaldo-wedding", N, ["Cristiano Ronaldo", "Georgina Rodriguez"]),
    ("polymarket", "3392828", "ronaldo-wedding", N, ["Cristiano Ronaldo", "Georgina Rodriguez"]),
    ("polymarket", "3342082", "ronaldo-wedding", N, ["Cristiano Ronaldo", "Georgina Rodriguez"]),
]


def main() -> None:
    reg = Registry()
    for venue, ref, family, detrend, keys in PANEL:
        m = v.FETCH[venue](ref, family)
        reg = reg.upsert(m.model_copy(update={"entity_keys": keys, "detrend": detrend}))
        print(f"{family:<20} {m.market_id:<42} {m.question[:60]}")
    save_registry(reg, OUT)
    families = {m.group for m in reg.markets}
    print(f"\n{len(reg.markets)} markets in {len(families)} families -> {OUT}")


if __name__ == "__main__":
    main()
