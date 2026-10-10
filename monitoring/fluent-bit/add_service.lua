function add_service(tag, timestamp, record)
    if record["service"] == nil then
        record["service"] = tag
    end
    return 2, timestamp, record
end
