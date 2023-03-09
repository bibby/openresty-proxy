----------------------------------------------
-- scenario: user has presented a client certificate
-- TRUST
--   nginx declared it valid.
-- BUT VERIFY
--   this openresty script take it steps further by dialing back
-- to the company LDAP, and verifying that the user
-- a) still works there, and b) is a member of the group we require

openssl = require "openssl"
ldap = require "lualdap"

base_domain = "dc=example,dc=com"
people_base = "ou=people," .. base_domain
posix_base = "ou=groups," .. base_domain
app_base = "ou=applications," .. base_domain
cache_ttl = 60 * 20 -- seconds

ldap_serv = assert (ldap.open_simple(
    "ldap_serv",
    "cn=readonly," .. base_domain,
    "readonly_password"
  )
)


function string:split(pat)
  pat = pat or '%s+'
  local st, g = 1, self:gmatch("()("..pat..")")
  local function getter(segs, seps, sep, cap1, ...)
    st = sep and seps + #sep
    return self:sub(segs, (seps or 0) - 1), cap1 or sep, ...
  end
  return function() if st then return getter(st, g()) end end
end

----------------------------------------------
-- pickle
----------------------------------------------

function pickle(t)
  return Pickle:clone():pickle_(t)
end

Pickle = {
  clone = function (t) local nt={}; for i, v in pairs(t) do nt[i]=v end return nt end
}

function Pickle:pickle_(root)
  if type(root) ~= "table" then
    error("can only pickle tables, not ".. type(root).."s")
  end
  self._tableToRef = {}
  self._refToTable = {}
  local savecount = 0
  self:ref_(root)
  local s = ""

  while table.getn(self._refToTable) > savecount do
    savecount = savecount + 1
    local t = self._refToTable[savecount]
    s = s.."{\n"
    for i, v in pairs(t) do
        s = string.format("%s[%s]=%s,\n", s, self:value_(i), self:value_(v))
    end
    s = s.."},\n"
  end

  return string.format("{%s}", s)
end

function Pickle:value_(v)
  local vtype = type(v)
  if     vtype == "string" then return string.format("%q", v)
  elseif vtype == "number" then return v
  elseif vtype == "boolean" then return tostring(v)
  elseif vtype == "table" then return "{"..self:ref_(v).."}"
  else --error("pickle a "..type(v).." is not supported")
  end
end

function Pickle:ref_(t)
  local ref = self._tableToRef[t]
  if not ref then
    if t == self then error("can't pickle the pickle class") end
    table.insert(self._refToTable, t)
    ref = table.getn(self._refToTable)
    self._tableToRef[t] = ref
  end
  return ref
end


function unpickle(s)
  if type(s) ~= "string" then
    error("can't unpickle a "..type(s)..", only strings")
  end
  local gentables = loadstring("return "..s)
  local tables = gentables()

  for tnum = 1, table.getn(tables) do
    local t = tables[tnum]
    local tcopy = {}; for i, v in pairs(t) do tcopy[i] = v end
    for i, v in pairs(tcopy) do
      local ni, nv
      if type(i) == "table" then ni = tables[i[1]] else ni = i end
      if type(v) == "table" then nv = tables[v[1]] else nv = v end
      t[i] = nil
      t[ni] = nv
    end
  end
  return tables[1]
end

function dumps(t,i)
  i = i or 0
  s = ""
	for k,v in pairs(t) do
		if(type(v)=='table') then
			s = s .. string.rep('\t',i) .. k .. '={'
			s = s .. (dumps(v,i+1))
			s = s .. (string.rep('\t',i) .. k .. '=} ')
		else
			s = s .. (string.rep('\t',i) .. k .. '=' .. tostring(v)) .. " "
		end
	end
  return s
end

----------------------------------------------
-- end pickle
----------------------------------------------

function get_common_name()
  ngx.log(ngx.DEBUG, ngx.var.ssl_client_raw_cert)

  client_cert = openssl.x509.read(ngx.var.ssl_client_raw_cert)
	ngx.log(ngx.DEBUG, dumps(client_cert:subject():info()))

  common_name = string.match(
    client_cert:subject():oneline(),
    "/CN=([^/]+)"
  )

  ngx.log(ngx.INFO, "common_name = " .. common_name)
  return common_name:gsub(".local$", "", 1)
end


function get_ldap_user(common_name)
  local query = {
    base = people_base,
    scope = "onelevel",
		sizelimit = 1,
    filter = "(&(objectClass=posixAccount)(|(!(employeeType=*))(employeeType=active)(employeeType=robot))(uid="..common_name.."))",
    attrs = {"cn", "uid"},
    attrs = false,
  }

  ngx.log(ngx.DEBUG, dumps(query))
  return ldap_query(query)[1]
end


function get_posix_groups(user)
  local query = {
    base = posix_base,
    scope = "onelevel",
    filter = "(&(objectClass=posixGroup)(memberUid=".. user.uid .."))",
    attrs = false,
  }

  ngx.log(ngx.DEBUG, dumps(query))
  return ldap_query(query)
end


function get_app_groups(user)
  local query = {
    base = app_base,
    scope = "subtree",
    filter = "(&(objectClass=groupOfNames)(member=" .. user.dn .. "))",
    attrs = false,
  }

  ngx.log(ngx.DEBUG, dumps(query))
  return ldap_query(query)
end

function ldap_query(query)
  -- try the cache first
  -- -- this shared dict is defined in site nginx conf `lua_shared_dict`
  local cache_ns = ngx.shared.cache
  local cache_key = "ldap|" .. query.filter
  local cached, _flags = cache_ns:get(cache_key)
  if cached == nil then
    ngx.log(ngx.INFO, "CACHE_MISS = " .. cache_key)
  else
    ngx.log(ngx.INFO, "CACHE_HIT = " .. cache_key)
    return unpickle(cached)
  end

  -- big expensive query
  ngx.log(ngx.INFO, "QUERY LDAP")
  local res_list = {}
  local debug_print = false
  for dn, attribs in ldap_serv:search(query) do
    local res = {}
    table.insert(res_list, res)
    ngx.log(ngx.INFO, "dn = " .. dn)

    res["dn"] = dn
    for name, values in pairs (attribs) do
      res[name] = values

      if debug_print then
        ngx.log(ngx.DEBUG, "["..name.."] : ")
        if type (values) == "string" then
          ngx.log(ngx.DEBUG, values)
        elseif type (values) == "table" then
          local n = table.getn(values)
          for i = 1, n do
            ngx.log(ngx.DEBUG, "-" .. values[i])
          end
        end
      end
    end
  end

  -- cache result
  local _cached, _err, _forcible = cache_ns:set(
    cache_key,
    pickle(res_list),
    cache_ttl
  )
  ngx.log(ngx.INFO, "CACHE_SET = (" .. tostring(_cached) .. ") " .. cache_key)

  return res_list
end

-- this var defined in site nginx conf
required_group = ngx.var.required_group
ngx.log(ngx.INFO, "Required Group = " .. tostring(required_group))

if required_group then
  cname = get_common_name()
  ngx.var.cert_common_name = cname
  user = get_ldap_user(cname)

  posix_groups = get_posix_groups(user)
  num_posix_groups = table.getn(posix_groups)

  app_groups = get_app_groups(user)
  num_app_groups = table.getn(app_groups)

  ngx.log(ngx.DEBUG, "Posix Groups: " .. tostring(num_posix_groups))
  ngx.log(ngx.DEBUG, "App Groups: " .. tostring(num_app_groups))

  found = false
  for i = 1, num_posix_groups do
    if posix_groups[i].cn == required_group then
      ngx.log(ngx.INFO, "AUTHORIZED: " .. posix_groups[i].cn )
      found = true
    end
  end

  for i = 1, num_app_groups do
    local names = {}
    for component in app_groups[i].dn:split(",") do
      local comp_iter = component:split("=")
      local _burn = comp_iter()
      local value = comp_iter()
      table.insert(names, value)
    end

    local tag = table.concat({names[2], names[1]}, "/")
    ngx.log(ngx.DEBUG, "TAG: " .. tag )

    if tag == required_group then
      ngx.log(ngx.INFO, "AUTHORIZED: " .. tag )
      found = true
    end
  end

  if not found then
    ngx.log(ngx.WARN, "User not in required group")
    ngx.status = 401
    ngx.exit(ngx.status)
  end
else
  ngx.log(ngx.INFO, "LDAP Group not required")
end

ldap_serv:close()
ngx.log(ngx.INFO, "USER ALLOWED")
