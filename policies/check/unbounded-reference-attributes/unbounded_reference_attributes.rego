package after_resolution

import rego.v1

is_deprecated(obj) if {
    object.get(obj, "deprecated", null) != null
}

is_unbounded(attr) if {
    annotations := object.get(attr, "annotations", {})
    val_annotations := object.get(annotations, "value", {})
    object.get(val_annotations, "unbounded_size", false) == true
}

attribute_exists(key) if {
    some attr in input.registry.attributes
    attr.key == key
}

# Every non-deprecated attribute marked unbounded_size: true must have a corresponding *_ref attribute in the registry.
deny contains finding if {
    some attr in input.registry.attributes
    not is_deprecated(attr)
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

# Every non-deprecated span, event, or refinement that includes a local unbounded attribute must also include its *_ref attribute.
deny contains finding if {
    some signal in signals
    some attr in signal.attributes
    not is_deprecated(attr)
    attribute_exists(attr.key)
    is_unbounded(attr)
    ref_key := concat("", [attr.key, "_ref"])
    not signal_has_attribute(signal, ref_key)

    finding := {
        "id": "signal_unbounded_attribute_missing_ref",
        "context": {
            "attribute_key": attr.key,
            "expected_ref_key": ref_key,
        },
        "message": sprintf("%s '%s' includes unbounded attribute '%s' and must also include '%s'.", [signal.signal_type, signal.signal_name, attr.key, ref_key]),
        "level": "violation",
        "signal_type": signal.signal_type,
        "signal_name": signal.signal_name,
    }
}

signal_has_attribute(signal, key) if {
    some a in signal.attributes
    a.key == key
}

base_span_exists(id) if {
    some s in input.registry.spans
    s.type == id
}

base_event_exists(id) if {
    some e in input.registry.events
    e.name == id
}

signals contains entry if {
    some span in input.registry.spans
    not is_deprecated(span)
    entry := {"signal_type": "span", "signal_name": span.type, "attributes": object.get(span, "attributes", [])}
}

signals contains entry if {
    some event in input.registry.events
    not is_deprecated(event)
    entry := {"signal_type": "event", "signal_name": event.name, "attributes": object.get(event, "attributes", [])}
}

signals contains entry if {
    some span in object.get(object.get(input, "refinements", {}), "spans", [])
    not base_span_exists(span.id)
    not is_deprecated(span)
    entry := {"signal_type": "span", "signal_name": span.id, "attributes": object.get(span, "attributes", [])}
}

signals contains entry if {
    some event in object.get(object.get(input, "refinements", {}), "events", [])
    not base_event_exists(event.id)
    not is_deprecated(event)
    entry := {"signal_type": "event", "signal_name": event.id, "attributes": object.get(event, "attributes", [])}
}
