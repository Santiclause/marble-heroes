import itertools, math, collections, bisect
class Item(object):
    def __init__(self, name, category, stats):
        self.name = name
        self.category = category
        self.stats = stats
    def __repr__(self):
        return "<Item: '{}', {}>".format(self.name, self.category)
    def __eq__(self, other):
        return self.name == other

class Skill(object):
    def __init__(self, name, tags, stats, dps, ranks):
        self.name = name
        self.tags = tags
        self.stats = stats
        self.dps = dps
        self.ranks = ranks
        self.filler = 'filler' in tags

    def __repr__(self):
        return "<Skill: {}>".format(self.name)

    def calculate_rank(self, item_stats):
        power_name = self.name.replace(' ', '-')
        powers = get_stat(item_stats, self.tags, 'powers') + item_stats.get('power-' + power_name, 0)
        return min(powers + self.ranks, 50)

    def get_stats(self, item_stats):
        if not self.stats:
            return {}
        ranks = self.calculate_rank(item_stats)
        return dict((s, self.stats[s][0] + (ranks-1)*self.stats[s][1]) for s in self.stats)

    def calculate(self, stats, filler_dps=0):
        if not self.dps:
            return 0
        x = self.dps
        dps = ((x['dmg_min'] + x['dmg_max'])/2 + x['dot']*x['dot_duration']*2)/x['period']
        dps *= calculate_multiplier(stats, self.tags)
        if 'aspd_period' in self.tags:
            dps *= 1 + calculate_aspd(stats.get('aspd', 0))
        if filler_dps:
            anim = x['anim_time']
            if 'aspd' in self.tags:
                anim /= 1 + calculate_aspd(stats.get('aspd', 0))
            dps -= filler_dps*anim/x['period']
        rank = self.calculate_rank(stats)
        dps *= rank*0.1 + 0.9
        return dps

class EmmaSkill(Skill):
    def calculate(self, stats, filler_dps=0):
        dps = super(EmmaSkill, self).calculate(stats)
        if not dps:
            return 0
        if 'diamond' in self.tags:
            defense = stats.get('def', 0)
            def_percent = stats['percent-def'] + stats['dur']*2
            dps *= 1 + defense*(def_percent + 100)/(100*100*250)
        if filler_dps:
            x = self.dps
            anim = x['anim_time']
            if 'aspd' in self.tags:
                anim /= 1 + calculate_aspd(stats.get('aspd', 0))
            dps -= filler_dps*anim/x['period']
        return dps

def calculate_aspd(base):
    if not base:
        return base
    return 0.4*(1 - math.exp(-3 * base/100))

def calculate_multiplier(stats, tags):
    dmg_stat = stats.get("phys" in tags and "str" or "energy", 0)
    intel = stats.get('int', 0)
    fight = stats.get('fight', 0)
    dmg = get_stat(stats, tags, 'dmg')
    dmg_per = get_stat(stats, tags, 'percent-dmg')
    csr = get_stat(stats, tags, 'chr') + 30*intel
    crit = get_stat(stats, tags, 'percent-crit')
    bsr = get_stat(stats, tags, 'bsr') + 60*fight
    brut = get_stat(stats, tags, 'percent-brut')
    cdr = get_stat(stats, tags, 'cdr') + 90*intel
    crit_dmg = get_stat(stats, tags, 'percent-crit-dmg')
    bdr = get_stat(stats, tags, 'bdr') + 180*fight
    brut_dmg = get_stat(stats, tags, 'percent-brut-dmg')
    crit_chance = 'crit' in tags and 1 or 99*csr/(100*(csr + 3601)) + crit/100
    brut_chance = 'brut' in tags and 1 or 75*bsr/(100*(bsr + 3601)) + brut/100
    damage = 1 + dmg/4000 + (dmg_per + 4*dmg_stat + 3*fight)/100
    crit_damage = (150 + 0.75*cdr/60)/100 + crit_dmg/100
    brut_damage = (300 + 0.75*(cdr + bdr)/60)/100 + brut_dmg/100
    return damage*(1 + crit_chance*(crit_damage*(1 - brut_chance) + brut_chance*brut_damage - 1))

def calculate_skills(stats, skills):
    filler = filter(lambda s: s.filler, skills)
    not_filler = filter(lambda s: not s.filler, skills)
    def do_twice(do_filler=False):
        dps = {}
        highest = (None, 0)
        for s in filler:
            x = s.calculate(stats)
            if x > highest[1]:
                highest = (s, x)
            dps[s.name] = (s, x)
        dps.update(dict((s.name, (s, s.calculate(stats, do_filler and highest[1] or 0))) for s in not_filler))
        return dps
    dps = do_twice()
    missing = []
    for s, x in dps.values():
        rank = s.calculate_rank(stats)
        base = x/(rank*0.1 + 0.9)
        if rank < 50:
            bisect.insort(missing, (base, 50 - rank, s))
    count = 4
    for base, diff, s in reversed(missing):
        add = min(count, diff)
        count -= add
        stats['power-' + s.name.replace(' ', '-')] += add
        if not count:
            break
        if count < 0:
            raise Exception('what the fuck happen')
    return do_twice(True)

def get_stat(stats, tags, stat):
    return stats.get(stat, 0) + sum(stats.get(stat + '_' + tag, 0) for tag in tags)

def parse_item(line):
    line = line.strip()
    if line[0] == "#":
        return None
    info, stats = line.split(": ", 1)
    name, category = info.split(", ", 1)
    stats = dict((x[1], float(x[0])) for x in map(lambda s: s.split(" ", 1), stats.split(", ")))
    #return (name, category, stats)
    return Item(name, category, stats)

def parse_skill(line, dps_header="dmg_min dmg_max dot dot_duration period anim_time".split(' ')):
    line = line.strip()
    name, info = line.split(': ')
    tags, stats_string, dps_string, ranks = info.split(';')
    tags = tags.split(' ')
    dps = dict(zip(dps_header, dps_string and map(float, dps_string.split(' ')) or []))
    stats = {}
    if stats_string:
        #do stats stuff
        for s in itertools.imap(lambda s: s.split(' '), stats_string.split(', ')):
            stats[s[2]] = (float(s[0]), float(s[1]))
    ranks = int(ranks)
    return EmmaSkill(name, tags, stats, dps, ranks)

def calculate_stats(items, skills):
    stats = collections.defaultdict(lambda: 0)
    for item in items:
        for stat in item.stats:
            stats[stat] += item.stats[stat]
    stats['aspd'] += stats.get('speed', 0)
    stats['hp'] += stats['dur']*360
    for skill in skills:
        for stat, val in skill.get_stats(stats).iteritems():
            stats[stat] += val
    return stats

def print_items(item_list):
    x = collections.defaultdict(list)
    for i in item_list:
        x[i.category].append(i)
    for cat in items:
        if len(items[cat]) <= limits[cat]:
            x.pop(cat)
    for key in sorted(x.keys()):
        print "{:15}{}".format(key, ", ".join(y.name for y in x[key]))


def result_filter(results, contains=[], excludes=[]):
    return list(r for r in results if all(c in r[1] for c in contains) and not any(e in r[1] for e in excludes))

with open('marble items.txt', 'r') as f:
    limits = dict((x[0], int(x[1])) for x in itertools.imap(lambda s: s.split(" "), f.readline().strip().split(", ")))
    items = collections.defaultdict(list)
    for item in itertools.imap(parse_item, f):
##        if item.category in items:
##            items[item.category][item.name] = item.stats
##        else:
##            items[item.category] = {item.name: item.stats}
        if not item:
            continue
        items[item.category].append(item)
with open('emma skills.txt', 'r') as f:
    skills = map(parse_skill, f)

def first_artis(results, artis=len(items['arti'])):
    first_arti = collections.defaultdict(lambda: 15504)
    for x in xrange(len(results)):
        for i in results[x][1]:
            if i.category == "arti":
                first_arti[i.name] = min(first_arti[i.name], x)
        if len(first_arti) >= artis:
            break
    return first_arti

def first(results, item):
    for x in xrange(len(results)):
        if item in results[x][1]:
            return x

def first_without(results, item):
    for x in xrange(len(results)):
        if not item in results[x][1]:
            return x
def nCr(n, r):
    f = math.factorial
    return f(n) / f(r) / f(n-r)

def check():
    prod = 1
    for cat in items:
        l = len(items[cat])
        if l > limits[cat]:
            prod *= nCr(l, limits[cat])
    return prod

print "This will take {} iterations.".format(check())
highest = (None, 0)
counter = 0
results = []
for i in itertools.product(*(itertools.combinations(items[cat], limits[cat]) for cat in items)):
    item_list = list(itertools.chain.from_iterable(i))
    stats = calculate_stats(item_list, skills)
    dps = calculate_skills(stats, skills)
    x = sum(v[1] for v in dps.values())
    if x > highest[1]:
        highest = ([item_list, stats, dps], x)
    counter += 1
    if not counter%10000:
        print counter
    bisect.insort(results, (x, item_list))
results = list(reversed(results))
