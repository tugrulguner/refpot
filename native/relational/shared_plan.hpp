#pragma once
#include "foundation.hpp"
#include <map>
#include <string>
#include <tuple>
#include <vector>

namespace refpot::relational {
struct SharedPlan {
    std::vector<foundation::Definition> logical_definitions, physical_definitions;
    std::map<std::string, std::string> logical_to_physical;
    std::vector<std::string> required;
};

inline auto definition_signature(const foundation::Definition& d) {
    return std::make_tuple(d.op, d.input, d.left, d.right, d.width, d.exprs,
                          d.column, d.cmp, d.value, d.left_key, d.right_key,
                          d.key, d.value_column, d.right_column);
}

inline SharedPlan compile_shared_plan(const std::vector<foundation::Definition>& logical,
                                      const std::vector<std::string>& required) {
    // Validate the logical graph before optimization can hide invalid definitions.
    foundation::Model validated(logical, required);
    SharedPlan out;
    out.logical_definitions = logical;
    out.required = required;
    using Signature = decltype(definition_signature(foundation::Definition{}));
    std::map<Signature, std::string> fingerprints;
    std::map<std::string, std::size_t> widths;
    for (const auto& original : logical) {
        auto d = original;
        if (d.op == "map" || d.op == "filter" || d.op == "group")
            d.input = out.logical_to_physical.at(d.input);
        if (d.op == "join" || d.op == "anti" || d.op == "union") {
            d.left = out.logical_to_physical.at(d.left);
            d.right = out.logical_to_physical.at(d.right);
        }
        // Do not commute joins: output column ordering is part of their meaning.
        const auto width = d.op == "source" ? d.width : d.op == "map" ? d.exprs.size() :
            d.op == "group" ? 3 : d.op == "join" ? widths.at(d.left) + widths.at(d.right) :
            widths.at(d.op == "filter" ? d.input : d.left);
        bool identity = d.op == "map" && d.exprs.size() == widths.at(d.input);
        if (identity) for (std::size_t i = 0; i < d.exprs.size(); ++i)
            if (d.exprs[i] != std::vector<std::string>{"c" + std::to_string(i)}) identity = false;
        std::string target;
        if (identity) target = d.input;
        else if (d.op == "source") {
            target = d.name;
            out.physical_definitions.push_back(d);
        } else {
            const auto entry = fingerprints.emplace(definition_signature(d), d.name);
            target = entry.first->second;
            if (entry.second) out.physical_definitions.push_back(d);
        }
        out.logical_to_physical.emplace(d.name, target);
        widths.emplace(d.name, width);
    }
    return out;
}
}
