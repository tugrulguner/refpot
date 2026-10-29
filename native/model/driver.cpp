// Experimental line-protocol harness, not the installed Python extension.
#include "model.hpp"
#include <charconv>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>

using namespace refpot::model;

namespace {
constexpr std::size_t limit = 4096;
std::string token(std::istringstream& in) {
    std::string s;
    if (!(in >> s)) throw std::invalid_argument("missing token");
    return s;
}
I integer(std::istringstream& in) {
    const auto s = token(in);
    I n = 0;
    const auto result = std::from_chars(s.data(), s.data() + s.size(), n);
    if (result.ec != std::errc{} || result.ptr != s.data() + s.size())
        throw std::invalid_argument("invalid signed integer");
    return n;
}
std::size_t count(std::istringstream& in) {
    const auto n = integer(in);
    if (n < 0 || n > static_cast<I>(limit)) throw std::invalid_argument("invalid count/index");
    return static_cast<std::size_t>(n);
}
std::string name(std::istringstream& in) {
    auto s = token(in);
    if (s.size() > 64 || s[0] < 'a' || s[0] > 'z')
        throw std::invalid_argument("invalid relation name");
    for (char c : s)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_'))
            throw std::invalid_argument("invalid relation name");
    return s;
}
void end(std::istringstream& in) {
    std::string s;
    if (in >> s) throw std::invalid_argument("trailing tokens");
}
std::string escaped(const std::string& s) {
    std::string out;
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += static_cast<char>(c); }
        else if (c < 32) out += '?';
        else out += static_cast<char>(c);
    }
    return out;
}
Definition definition(std::istringstream& in) {
    Definition d;
    d.op = token(in); d.name = name(in);
    if (d.op == "source") d.width = count(in);
    else if (d.op == "map") {
        d.input = name(in);
        auto n = count(in);
        for (std::size_t i = 0; i < n; ++i) {
            std::vector<std::string> expr;
            auto k = count(in);
            for (std::size_t j = 0; j < k; ++j) expr.push_back(token(in));
            d.exprs.push_back(std::move(expr));
        }
    } else if (d.op == "filter") {
        d.input = name(in); d.column = count(in); d.cmp = token(in); d.value = integer(in);
    } else if (d.op == "join" || d.op == "anti") {
        d.left = name(in); d.right = name(in);
        d.left_key = count(in); d.right_key = count(in);
    } else if (d.op == "group") {
        d.input = name(in); d.key = count(in); d.value_column = count(in);
    } else if (d.op == "union") { d.left = name(in); d.right = name(in); }
    else throw std::invalid_argument("unknown definition operator");
    end(in);
    return d;
}
void dump(const Model& model) {
    // Prepare the complete response before touching stdout.
    std::ostringstream out;
    out << "{\"ok\":true,\"epoch\":" << model.epoch() << ",\"tables\":{";
    bool first_table = true;
    for (const auto& [name, bag] : model.snapshot()) {
        if (!first_table) out << ',';
        first_table = false;
        out << '"' << escaped(name) << "\":[";
        bool first_row = true;
        for (const auto& [row, multiplicity] : bag) {
            if (!first_row) out << ',';
            first_row = false;
            out << '[';
            for (const auto value : row) out << value << ',';
            out << multiplicity << ']';
        }
        out << ']';
    }
    const auto stats = model.stats();
    out << "},\"stats\":{\"source_delta_rows\":" << stats.source_delta_rows
        << ",\"derived_nodes\":" << stats.derived_nodes
        << ",\"rows_visited\":" << stats.rows_visited
        << ",\"copied_rows\":" << stats.copied_rows << "}}";
    std::cout << out.str() << std::endl;
}
}

int main() {
    std::vector<Definition> definitions;
    std::unique_ptr<Model> model;
    std::vector<Mutation> pending;
    bool active = false;
    std::string line;
    while (std::getline(std::cin, line)) {
        try {
            if (line.size() > 1024 * 1024) throw std::invalid_argument("request too long");
            std::istringstream in(line);
            const auto op = token(in);
            if (op == "DEF") {
                if (model) throw std::invalid_argument("model already sealed");
                if (definitions.size() >= limit) throw std::invalid_argument("too many nodes");
                auto d = definition(in);
                definitions.push_back(std::move(d));
            } else if (op == "SEAL") {
                if (model) throw std::invalid_argument("model already sealed");
                std::vector<std::string> constraints;
                auto n = count(in);
                for (std::size_t i = 0; i < n; ++i) constraints.push_back(name(in));
                end(in);
                model = std::make_unique<Model>(definitions, constraints);
            } else {
                if (!model) throw std::invalid_argument("model not sealed");
                if (op == "BEGIN") {
                    end(in);
                    if (active) throw std::invalid_argument("transaction already active");
                    pending.clear(); active = true;
                } else if (op == "INSERT" || op == "UPDATE" || op == "DELETE") {
                    if (!active) throw std::invalid_argument("no active transaction");
                    if (pending.size() >= 10000) throw std::invalid_argument("transaction too large");
                    Mutation mutation;
                    mutation.op = op == "INSERT" ? "insert" : op == "UPDATE" ? "update" : "delete";
                    mutation.table = name(in);
                    if (op == "DELETE") mutation.key = integer(in);
                    else {
                        auto n = count(in);
                        for (std::size_t i = 0; i < n; ++i) mutation.row.push_back(integer(in));
                    }
                    end(in);
                    pending.push_back(std::move(mutation));
                } else if (op == "COMMIT") {
                    end(in);
                    if (!active) throw std::invalid_argument("no active transaction");
                    active = false;
                    auto batch = std::move(pending);
                    pending.clear();
                    model->apply(batch);
                } else if (op == "ROLLBACK") {
                    end(in);
                    if (!active) throw std::invalid_argument("no active transaction");
                    pending.clear(); active = false;
                } else if (op == "SNAPSHOT") {
                    end(in); dump(*model); continue;
                } else throw std::invalid_argument("unknown command");
            }
            std::cout << "{\"ok\":true}" << std::endl;
        } catch (const std::exception& error) {
            // A rejected request invalidates the entire staged transaction, including
            // earlier well-formed requests. Never allow a later partial COMMIT.
            pending.clear();
            active = false;
            std::cout << "{\"ok\":false,\"error\":\"" << escaped(error.what()) << "\"}" << std::endl;
        }
    }
}
