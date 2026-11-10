package after_resolution

import rego.v1

is_unbounded(attr) if {
    annotations := object.get(attr, "annotations", {})
    val_annotations := object.get(annotations, "value", {})
    object.get(val_annotations, "unbounded_size", false) == true
}

is_unbounded_key(key) if {
    some attr in input.registry.attributes
    attr.key == key
    is_unbounded(attr)
}

attribute_exists(key) if {
    some attr in input.registry.attributes
    attr.key == key
}

# Every attribute marked unbounded_size: true must have a corresponding *_ref attribute in the registry.
deny contains finding if {
    some attr in input.registry.attributes
    is_unbounded(attr)
    ref_key := concat("", [attr.key, "_ref"])
    not attribute_exists(ref_key)

    finding := {
        "id": "unbounded_attribute_missing_ref",
        "context": {
            "attribute_key": attr.key,
            "expected_ref_key": ref_key,
        },
        "message": sprintf("Attribute '%s' has annotations.value.unbounded_size: true and must have a corresponding '%s' attribute in the registry.", [attr.key, ref_key]),
        "level": "violation",
    }
}

# Every *_ref attribute must have a base attribute marked unbounded_size: true.
deny contains finding if {
    some attr in input.registry.attributes
    endswith(attr.key, "_ref")
    base_key := substring(attr.key, 0, count(attr.key) - 4)
    attribute_exists(base_key)
    not is_unbounded_key(base_key)

    finding := {
        "id": "reference_attribute_counterpart_not_unbounded",
        "context": {
            "attribute_key": attr.key,
            "base_key": base_key,
        },
        "message": sprintf("Reference attribute '%s' requires counterpart attribute '%s' to set annotations.value.unbounded_size: true.", [attr.key, base_key]),
        "level": "violation",
    }
}

# Every span or event that includes an unbounded attribute must also include its *_ref attribute.
deny contains finding if {
    some signal in signals
    some attr in signal.attributes
    is_unbounded_key(attr.key)
    ref_key := concat("", [attr.key, "_ref"])
    not signal_has_attribute(signal, ref_key)

    finding := {
        "id": "signal_unbounded_attribute_missing_ref",
        "context": {
            "signal_type": signal.signal_type,
            "signal_name": signal.signal_name,
            "attribute_key": attr.key,
            "expected_ref_key": ref_key,
        },
        "message": sprintf("%s '%s' includes unbounded attribute '%s' and must also include '%s'.", [signal.signal_type, signal.signal_name, attr.key, ref_key]),
        "level": "violation",
    }
}

# Every span or event that includes a *_ref attribute must also include its base attribute.
deny contains finding if {
    some signal in signals
    some attr in signal.attributes
    endswith(attr.key, "_ref")
    base_key := substring(attr.key, 0, count(attr.key) - 4)
    not signal_has_attribute(signal, base_key)

    finding := {
        "id": "signal_reference_attribute_missing_base",
        "context": {
            "signal_type": signal.signal_type,
            "signal_name": signal.signal_name,
            "attribute_key": attr.key,
            "expected_base_key": base_key,
        },
        "message": sprintf("%s '%s' includes reference attribute '%s' and must also include '%s'.", [signal.signal_type, signal.signal_name, attr.key, base_key]),
        "level": "violation",
    }
}

signal_has_attribute(signal, key) if {
    some a in signal.attributes
    a.key == key
}

signals contains entry if {
    some span in input.registry.spans
    entry := {"signal_type": "Span", "signal_name": span.type, "attributes": span.attributes}
}

signals contains entry if {
    some event in input.registry.events
    entry := {"signal_type": "Event", "signal_name": event.name, "attributes": event.attributes}
}
