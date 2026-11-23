-- UK walking rules for OSRM (docs/superpowers/specs/2026-11-22-walking-rules-and-reachable-pharmacies-design.md).
--
-- OSRM's stock foot.lua, loaded unchanged, plus:
--   * cycle paths, unless tagged foot=no. Cycle paths not signed for walkers (no foot=yes,
--     designated or permissive) get the excludable class "cycleway", so the pipeline can tell
--     when a walk needs one;
--   * bridleways (pedestrians have a legal right of way);
--   * trunk roads, only where a pavement or foot access is tagged.
api_version = 4

-- OSRM puts the profile's own folder on the Lua path; the stock profile's require('lib/...')
-- needs /opt as well.
package.path = '/opt/?.lua;' .. package.path
local stock = dofile('/opt/foot.lua')

local FOOT_OK = Set { 'yes', 'designated', 'permissive' }
local PAVEMENT = Set { 'both', 'left', 'right', 'yes' }
local SIDEWALK_KEYS = { 'sidewalk', 'sidewalk:both', 'sidewalk:left', 'sidewalk:right' }

local function has_pavement(way)
  for _, key in ipairs(SIDEWALK_KEYS) do
    if PAVEMENT[way:get_value_by_key(key)] then
      return true
    end
  end
  return false
end

local function setup()
  local profile = stock.setup()
  for _, highway in ipairs({ 'cycleway', 'bridleway', 'trunk', 'trunk_link' }) do
    profile.speeds.highway[highway] = profile.default_speed
  end
  profile.classes = Sequence { 'cycleway' }
  profile.excludable = Sequence { Set { 'cycleway' } }
  return profile
end

local function process_way(profile, way, result, relations)
  local highway = way:get_value_by_key('highway')
  local foot = way:get_value_by_key('foot')
  if (highway == 'trunk' or highway == 'trunk_link') and not FOOT_OK[foot] and not has_pavement(way) then
    return
  end
  stock.process_way(profile, way, result, relations)
  if highway == 'cycleway' and not FOOT_OK[foot] then
    result.forward_classes['cycleway'] = true
    result.backward_classes['cycleway'] = true
  end
end

return {
  setup = setup,
  process_way = process_way,
  process_node = stock.process_node,
  process_turn = stock.process_turn,
  process_relation = stock.process_relation,
}
