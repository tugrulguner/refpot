#include "relational/sql.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

namespace py = pybind11;
namespace sql = refpot::sqlpreview;

class PyDatabase {
    std::unique_ptr<sql::Database> database_;
    bool busy_=false;
    const pid_t process_ = ::getpid();
    const std::thread::id thread_ = std::this_thread::get_id();

    void check(bool allow_poison=false) const {
        if (process_ != ::getpid() || thread_ != std::this_thread::get_id())
            throw std::runtime_error("database belongs to its creating process and thread");
        if (!database_) throw std::runtime_error("database is closed");
        if (busy_) throw std::runtime_error("reentrant database operation is unsupported");
        if (!allow_poison && database_->poisoned()) throw std::runtime_error("uncertain SQL storage outcome; close and reopen the database");
    }
    static std::vector<std::string> names(py::handle value) {
        if(!PyList_CheckExact(value.ptr())&&!PyTuple_CheckExact(value.ptr())) throw py::type_error("relations must be an exact list or tuple");
        auto count=PySequence_Size(value.ptr()); if(count>128) throw py::value_error("too many authorized relations");
        std::vector<std::string> result; result.reserve(static_cast<std::size_t>(count));
        for(Py_ssize_t i=0;i<count;++i){py::object x=py::reinterpret_steal<py::object>(PySequence_GetItem(value.ptr(),i));if(!PyUnicode_CheckExact(x.ptr()))throw py::type_error("relation names must be exact strings");if(PyUnicode_GET_LENGTH(x.ptr())>64)throw py::value_error("relation name exceeds 64 bytes");auto name=py::cast<std::string>(x);if(name.size()>64)throw py::value_error("relation name exceeds 64 bytes");result.push_back(std::move(name));}
        return result;
    }
    static std::vector<sql::I> parameters(py::handle input) {
        if(!PyList_CheckExact(input.ptr())&&!PyTuple_CheckExact(input.ptr()))throw py::type_error("native parameters must be an exact list or tuple");
        auto count=PySequence_Size(input.ptr());if(count>8192)throw py::value_error("too many parameters");std::vector<sql::I> out;out.reserve(static_cast<std::size_t>(count));
        for(Py_ssize_t i=0;i<count;++i){py::object x=py::reinterpret_steal<py::object>(PySequence_GetItem(input.ptr(),i));if(!PyLong_CheckExact(x.ptr()))throw py::type_error("parameters must be exact integers");auto n=PyLong_AsLongLong(x.ptr());if(PyErr_Occurred())throw py::error_already_set();out.push_back(n);}return out;
    }

public:
    explicit PyDatabase(const std::string& mode, py::object path) {
        if (mode != "overlay" && mode != "modular")
            throw std::invalid_argument("mode must be 'overlay' or 'modular'");
        const auto selected=mode=="overlay"?refpot::foundation::Mode::Overlay:refpot::foundation::Mode::Modular;
        if(path.is_none()) database_=std::make_unique<sql::Database>(selected);
        else {
            if(!PyUnicode_Check(path.ptr())) throw py::type_error("native database path must be str or None");
            const auto filename=py::cast<std::string>(path);
            if(filename.empty() || filename.find('\0')!=std::string::npos)
                throw py::value_error("database path must be nonempty and NUL-free");
            database_=std::make_unique<sql::Database>(filename,selected);
        }
    }

    py::object execute(py::handle query, py::handle parameters, py::handle explain) {
        check();
        struct Guard { bool& busy; ~Guard() {busy=false;} } guard{busy_};
        busy_=true;
        const bool explaining=explain.ptr()==Py_True;
        try {
            if(!PyBool_Check(explain.ptr())) throw py::type_error("explain must be bool");
            if(!PyUnicode_Check(query.ptr())) throw py::type_error("query must be a SQL string");
            if(!PyList_CheckExact(parameters.ptr()) && !PyTuple_CheckExact(parameters.ptr()))
                throw py::type_error("native parameters must be an exact list or tuple");
            const auto count=PySequence_Size(parameters.ptr());
            if(count>8192) throw py::value_error("too many parameters");
            std::vector<sql::I> values;values.reserve(static_cast<std::size_t>(count));
            for(Py_ssize_t i=0;i<count;++i) {
                py::object value=py::reinterpret_steal<py::object>(PySequence_GetItem(parameters.ptr(),i));
                if(!PyLong_CheckExact(value.ptr())) throw py::type_error("parameters must be exact integers");
                const auto integer=PyLong_AsLongLong(value.ptr());
                if(PyErr_Occurred()) throw py::error_already_set();
                values.push_back(integer);
            }
            sql::Result result;
            try { result=database_->execute(py::cast<std::string>(query),values,explaining); }
            catch(const std::exception& error) {
                PyErr_SetString(PyExc_RuntimeError,error.what());
                throw py::error_already_set();
            }
            try {
                // Keep ownership through conversion: execution may have published.
                return py::cast(std::move(result));
            } catch(...) { database_.reset();throw; }
        } catch(...) {
            if(database_ && !explaining) database_->rollback();
            throw;
        }
    }

    py::dict query_context(py::handle relations) {
        check(); struct Guard{bool& b;~Guard(){b=false;}} guard{busy_};busy_=true;
        auto context=database_->query_context(names(relations));py::dict out;out["revision"]=py::int_(context.revision);py::list entries;
        for(const auto& r:context.relations){py::dict item;item["name"]=r.name;item["columns"]=r.columns;item["derived"]=r.derived;entries.append(std::move(item));}out["relations"]=std::move(entries);return out;
    }
    py::object execute_readonly(py::handle query,py::handle params,py::handle relations,py::handle revision,py::handle explain) {
        check();struct Guard{bool& b;~Guard(){b=false;}} guard{busy_};busy_=true;
        if(!PyUnicode_CheckExact(query.ptr()))throw py::type_error("query must be an exact SQL string");
        if(!PyBool_Check(explain.ptr()))throw py::type_error("explain must be bool");
        if(!PyLong_CheckExact(revision.ptr()))throw py::type_error("revision must be an exact integer");
        auto token=PyLong_AsUnsignedLongLong(revision.ptr());if(PyErr_Occurred())throw py::error_already_set();
        auto result=database_->execute_readonly(py::cast<std::string>(query),parameters(params),names(relations),token,explain.ptr()==Py_True);
        return py::cast(std::move(result));
    }

    bool closed() const noexcept { return !database_; }

    bool in_transaction() const {
        check(true);
        return database_->in_transaction();
    }

    std::map<std::string, std::uint64_t> stats() const {
        check();
        return database_->stats();
    }

    void rollback() {
        check(true);
        database_->rollback();
    }

    void checkpoint() {
        check();
        database_->checkpoint();
    }

    void close() {
        if (process_ != ::getpid() || thread_ != std::this_thread::get_id())
            throw std::runtime_error("database belongs to its creating process and thread");
        if(busy_) throw std::runtime_error("reentrant database operation is unsupported");
        database_.reset();
    }
};

PYBIND11_MODULE(_sql, module) {
    module.doc() = "Native SQL preview engine with optional whole-model persistence";
    py::class_<sql::Result>(module, "_Result")
        .def_readonly("columns", &sql::Result::columns)
        .def_readonly("rows", &sql::Result::rows)
        .def_readonly("affected", &sql::Result::affected)
        .def_readonly("plan", &sql::Result::plan);
    py::class_<PyDatabase>(module, "_Database")
        .def(py::init<const std::string&,py::object>(), py::arg("mode") = "overlay", py::arg("path") = py::none())
        .def("execute", &PyDatabase::execute, py::arg("query"), py::arg("parameters"),
             py::arg("explain") = false)
        .def("query_context", &PyDatabase::query_context, py::arg("relations"))
        .def("execute_readonly", &PyDatabase::execute_readonly, py::arg("query"), py::arg("parameters"),
             py::arg("relations"), py::arg("revision"), py::arg("explain") = false)
        .def("closed", &PyDatabase::closed)
        .def("in_transaction", &PyDatabase::in_transaction)
        .def("stats", &PyDatabase::stats)
        .def("checkpoint", &PyDatabase::checkpoint)
        .def("rollback", &PyDatabase::rollback)
        .def("close", &PyDatabase::close);
}
