#pragma once
#include "../model/model.hpp"
#include <optional>

namespace refpot::relational {
using I = model::I;
using Row = model::Row;

// Both SQL binding and maintained filters resolve their spelling once. Rows
// execute this bound operator; neither consumer interprets comparison strings.
enum class Comparison { Equal, NotEqual, Less, LessEqual, Greater, GreaterEqual };
struct BoundPredicate {
    std::size_t column;
    Comparison operation;
    I value;
    std::optional<std::size_t> right_column=std::nullopt;
    static BoundPredicate bind(std::size_t column, const std::string& op, I value) {
        Comparison c;
        if (op=="=" || op=="eq") c=Comparison::Equal;
        else if (op=="!=" || op=="<>" || op=="ne") c=Comparison::NotEqual;
        else if (op=="<" || op=="lt") c=Comparison::Less;
        else if (op=="<=" || op=="le") c=Comparison::LessEqual;
        else if (op==">" || op=="gt") c=Comparison::Greater;
        else if (op==">=" || op=="ge") c=Comparison::GreaterEqual;
        else throw std::invalid_argument("unsupported comparison");
        return {column,c,value};
    }
    bool matches(const Row& row) const noexcept {
        I input=row[column]; // columns bound against the declared row width
        I value=right_column?row[*right_column]:this->value;
        switch(operation) {
            case Comparison::Equal: return input==value;
            case Comparison::NotEqual: return input!=value;
            case Comparison::Less: return input<value;
            case Comparison::LessEqual: return input<=value;
            case Comparison::Greater: return input>value;
            case Comparison::GreaterEqual: return input>=value;
        }
        return false;
    }
};

// The same checked count and wide integer sum serve SQL and maintained groups.
// Positive multiplicity and a checked total count bound the wide sum to 128 bits.
struct Aggregate {
    I count=0;
    __int128 sum=0;
    void add(I value,I multiplicity=1) {
        if(multiplicity<0)throw std::logic_error("aggregate needs visible multiplicity");
        count=model::detail::checked(static_cast<__int128>(count)+multiplicity);
        sum+=static_cast<__int128>(value)*multiplicity;
    }
    I value() const { return model::detail::checked(sum); }
};
}
