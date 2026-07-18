/* eslint-disable */
/**
 * Manually updated to match backend/src/schemas.py.
 * TODO: set up auto-generation from FastAPI OpenAPI spec.
 */

export type WinnerTeam = number | null;
export type RoundNum = number;
export type CurrentTeam = number;
export type ActiveEntity = number | null;
export type Id = number;
export type Name = string;
export type Hp = number;
export type Point = [number, number];
export type Team = number;
export type MoveActions = number;
export type StandardActions = number;
export type FreeActions = number;
export type Modifiers = string[];
export type Entities = EntityState[];

export interface GameLog {
  winner_team: WinnerTeam;
  logs: LogEntry[];
  [k: string]: unknown;
}

export interface LogEntry {
  state: EngineState;
  events: EventDescription[];
  messages?: string[];
  action_logs?: string[];
  done: boolean;
  [k: string]: unknown;
}

export interface EventDescription {
  type: string;
  actor_id?: number | null;
  target_id?: number | null;
  ability_name?: string | null;
  amount?: number | null;
  move_path?: Point[] | null;
  source_id?: number | null;
  target_pos?: Point | null;
  source_pos?: Point | null;
  [k: string]: unknown;
}

export interface EngineState {
  round_num: RoundNum;
  current_team: CurrentTeam;
  active_entity: ActiveEntity;
  entities: Entities;
  [k: string]: unknown;
}

export interface EntityState {
  id: Id;
  name: Name;
  hp: Hp;
  pos: Point | null;
  team: Team;
  move_actions: MoveActions;
  standard_actions: StandardActions;
  free_actions: FreeActions;
  modifiers?: Modifiers;
  is_object?: boolean;
  [k: string]: unknown;
}

export interface ActionState {
  actor: Actor;
  target: Target | null;
  ability: Ability;
  move_path?: Point[] | null;
  movement_name?: MovementName;
  [k: string]: unknown;
}
