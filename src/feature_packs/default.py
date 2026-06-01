from features import FeatureContext, WeightedFeature


def damage_to_enemy_ranged(ctx: FeatureContext) -> int:
    enemy = ctx.get_enemy_by_name("Ranged Hero")
    if not enemy:
        return 0
    return ctx.damage_dealt(enemy)


def damage_to_enemies(ctx: FeatureContext) -> int:
    return sum(ctx.damage_dealt(e) for e in ctx.enemies)


def healing_done_to_allies(ctx: FeatureContext) -> int:
    return sum(ctx.heal_received(a) for a in ctx.allies)


def enemies_killed(ctx: FeatureContext) -> int:
    return sum(1 for e in ctx.enemies if ctx.new_hp(e) is not None and ctx.new_hp(e) <= 0)


def self_hp(ctx: FeatureContext) -> int | None:
    return ctx.new_hp(ctx.actor)


def enemy_ranged_hero_hp_le_3(ctx: FeatureContext) -> bool:
    ranged_heroes = ctx.get_enemies_by_name("Ranged Hero")
    return any(ctx.new_hp(e) is not None and ctx.new_hp(e) <= 3 for e in ranged_heroes)


def do_nothing_on_turn_4(ctx: FeatureContext) -> bool:
    return ctx.choice.ability.name == "Do Nothing" and ctx.engine.round_num == 4


def allied_melee_near_enemy_ranged(ctx: FeatureContext) -> bool:
    allied_melee = ctx.get_allies_by_name("Melee Hero")
    enemy_ranged = ctx.get_enemies_by_name("Ranged Hero")
    return any(
        ctx.new_distance(am, er) is not None and ctx.new_distance(am, er) <= 2
        for am in allied_melee
        for er in enemy_ranged
    )


def used_ranged_attack(ctx: FeatureContext) -> bool:
    return (
        ctx.choice.ability.name == "Ranged Attack" and ctx.actor.name == "Ranged Hero"
    )


def number_of_enemies_hit(ctx: FeatureContext) -> int:
    return len(ctx.hit_enemies)


FEATURES = [
    WeightedFeature(
        name="Damage to enemy Ranged",
        eval_func=damage_to_enemy_ranged,
        weight=1.2,
    ),
    WeightedFeature(
        name="Damage to enemies",
        eval_func=damage_to_enemies,
        weight=1.0,
    ),
    WeightedFeature(
        name="Healing done to allies",
        eval_func=healing_done_to_allies,
        weight=1.5,
    ),
    WeightedFeature(
        name="Enemies killed",
        eval_func=enemies_killed,
        weight=100.0,
    ),
    WeightedFeature(name="Self HP", eval_func=self_hp, weight=0.1),
    WeightedFeature(
        name="Enemy Ranged Hero has HP <= 3",
        eval_func=enemy_ranged_hero_hp_le_3,
        weight=10.0,
    ),
    WeightedFeature(
        name="Do Nothing used on turn 4",
        eval_func=do_nothing_on_turn_4,
        weight=-50.0,
    ),
    WeightedFeature(
        name="Allied Melee near enemy Ranged",
        eval_func=allied_melee_near_enemy_ranged,
        weight=5.0,
    ),
    WeightedFeature(
        name="Used Ranged Attack",
        eval_func=used_ranged_attack,
        weight=1.5,
    ),
    WeightedFeature(
        name="Number of Enemies Hit",
        eval_func=number_of_enemies_hit,
        weight=2.0,
    ),
]
