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

    void check() const {
        if (process_ != ::getpid() || thread_ != std::this_thread::get_id())
            throw std::runtime_error("database belongs to its creating process and thread");
        if (!database_) throw std::runtime_error("database is closed");
        if (busy_) throw std::runtime_error("reentrant database operation is unsupported");
    }

public:
    explicit PyDatabase(const std::string& mode) {
        if (mode == "overlay")
            database_ = std::make_unique<sql::Database>(refpot::foundation::Mode::Overlay);
        else if (mode == "modular")
            database_ = std::make_unique<sql::Database>(refpot::foundation::Mode::Modular);
        else
            throw std::invalid_argument("mode must be 'overlay' or 'modular'");
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

    bool closed() const noexcept { return !database_; }

    bool in_transaction() const {
        check();
        return database_->in_transaction();
    }

    std::map<std::string, std::uint64_t> stats() const {
        check();
        return database_->stats();
    }

    void rollback() {
        check();
        database_->rollback();
    }

    void close() {
        if (process_ != ::getpid() || thread_ != std::this_thread::get_id())
            throw std::runtime_error("database belongs to its creating process and thread");
        if(busy_) throw std::runtime_error("reentrant database operation is unsupported");
        database_.reset();
    }
};

PYBIND11_MODULE(_sql, module) {
    module.doc() = "Native volatile SQL preview engine";
    py::class_<sql::Result>(module, "_Result")
        .def_readonly("columns", &sql::Result::columns)
        .def_readonly("rows", &sql::Result::rows)
        .def_readonly("affected", &sql::Result::affected)
        .def_readonly("plan", &sql::Result::plan);
    py::class_<PyDatabase>(module, "_Database")
        .def(py::init<const std::string&>(), py::arg("mode") = "overlay")
        .def("execute", &PyDatabase::execute, py::arg("query"), py::arg("parameters"),
             py::arg("explain") = false)
        .def("closed", &PyDatabase::closed)
        .def("in_transaction", &PyDatabase::in_transaction)
        .def("stats", &PyDatabase::stats)
        .def("rollback", &PyDatabase::rollback)
        .def("close", &PyDatabase::close);
}
