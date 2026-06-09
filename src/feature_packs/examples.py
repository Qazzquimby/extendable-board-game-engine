from features import FeatureContext, WeightedFeature


def damage_to_enemy_mr_example(ctx: FeatureContext) -> int:
    enemy = ctx.get_enemy_by_name("Mr. Example")
    if not enemy:
        return 0
    return ctx.damage_dealt(enemy)


def damage_to_enemies(ctx: FeatureContext) -> int:
    return sum(ctx.damage_dealt(e) for e in ctx.enemies)


def healing_done_to_allies(ctx: FeatureContext) -> int:
    return sum(ctx.heal_received(a) for a in ctx.allies)


def enemies_killed(ctx: FeatureContext) -> int:
    return sum(
        1 for e in ctx.enemies if ctx.new_hp(e) is not None and ctx.new_hp(e) <= 0
    )


def self_hp(ctx: FeatureContext) -> int | None:
    return ctx.new_hp(ctx.actor)


def enemy_mr_example_hp_le_3(ctx: FeatureContext) -> bool:
    mr_examples = ctx.get_enemies_by_name("Mr. Example")
    return any(ctx.new_hp(e) is not None and ctx.new_hp(e) <= 3 for e in mr_examples)


def do_nothing_on_turn_4(ctx: FeatureContext) -> bool:
    return ctx.choice.ability.name == "Do Nothing" and ctx.engine.round_num == 4


def allied_hero_near_enemy_mr_example(ctx: FeatureContext) -> bool:
    enemy_mr_example = ctx.get_enemies_by_name("Mr. Example")
    return any(
        ctx.new_distance(am, er) is not None and ctx.new_distance(am, er) <= 2
        for am in ctx.allies
        for er in enemy_mr_example
    )


def use_example_strike(ctx: FeatureContext) -> bool:
    return (
        ctx.choice.ability.name == "Example Strike" and ctx.actor.name == "Mr. Example"
    )


def number_of_enemies_hit(ctx: FeatureContext) -> int:
    return len(ctx.hit_enemies)


def distance_to_nearest_enemy(ctx: FeatureContext) -> int:
    return min(
        (
            ctx.new_distance(ctx.actor, e)
            for e in ctx.enemies
            if ctx.new_distance(ctx.actor, e) is not None
        ),
        default=0,
    )


FEATURES = [
    WeightedFeature(
        name="Damage to enemy Mr. Example",
        eval_func=damage_to_enemy_mr_example,
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
        name="Enemy Mr. Example has HP <= 3",
        eval_func=enemy_mr_example_hp_le_3,
        weight=10.0,
    ),
    WeightedFeature(
        name="Do Nothing used on turn 4",
        eval_func=do_nothing_on_turn_4,
        weight=-50.0,
    ),
    WeightedFeature(
        name="Ally near enemy Mr. Example",
        eval_func=allied_hero_near_enemy_mr_example,
        weight=5.0,
    ),
    WeightedFeature(
        name="Used Example Strike",
        eval_func=use_example_strike,
        weight=1.5,
    ),
    WeightedFeature(
        name="Number of Enemies Hit",
        eval_func=number_of_enemies_hit,
        weight=2.0,
    ),
    WeightedFeature(
        name="distance to nearest enemy",
        eval_func=distance_to_nearest_enemy,
        weight=-1,
    ),
]
