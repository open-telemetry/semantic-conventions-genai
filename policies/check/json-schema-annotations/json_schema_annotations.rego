package after_resolution

import rego.v1

has_json_schema_annotation(attr) if {
    path := json_schema_path(attr)
    trim(path, " \n\t") != ""
}

json_schema_path(attr) := path if {
    annotations := object.get(attr, "annotations", {})
    type_annotations := object.get(annotations, "type", {})
    path := object.get(type_annotations, "json_schema", "")
    is_string(path)
}

# Any complex attribute (type: any) must define a JSON schema annotation.
deny contains finding if {
    some attr in input.registry.attributes
    attr.type == "any"
    not has_json_schema_annotation(attr)

    finding := {
        "id": "json_schema_annotation_missing",
        "context": {
            "attribute_key": attr.key,
            "attribute_type": attr.type,
        },
        "message": sprintf("Attribute '%s' has type 'any' and must define annotations.type.json_schema.", [attr.key]),
        "level": "violation",
    }
}
