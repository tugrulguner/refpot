#include "sql.hpp"
#include <cassert>
#include <type_traits>
#include <iostream>
using namespace refpot::sqlpreview;
template<class T> void check(){
    if constexpr(!std::is_constructible_v<T,refpot::foundation::Mode,std::size_t>){
        assert(false&&"global catalog row budget must be injectable and enforced");
    }else for(auto mode:{refpot::foundation::Mode::Modular,refpot::foundation::Mode::Overlay}){
        T db(mode,3);
        db.execute("CREATE TABLE a (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
        db.execute("CREATE TABLE b (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
        db.execute("INSERT INTO a VALUES (1,10)");db.execute("INSERT INTO a VALUES (2,20)");
        db.execute("INSERT INTO b VALUES (1,30)");
        bool rejected=false;try{db.execute("INSERT INTO b VALUES (2,40)");}catch(const std::runtime_error&){rejected=true;}
        assert(rejected&&db.execute("SELECT COUNT(*) FROM b").rows[0][0]==1);
        db.execute("CREATE TABLE c (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
        assert(db.execute("SELECT COUNT(*) FROM a").rows[0][0]==2);
        db.execute("BEGIN");db.execute("DELETE FROM a WHERE id=1");db.execute("INSERT INTO c VALUES (1,50)");db.execute("COMMIT");
        assert(db.execute("SELECT COUNT(*) FROM a").rows[0][0]==1);
        db.execute("BEGIN");db.execute("UPDATE c SET value=60");
        rejected=false;try{db.execute("INSERT INTO c VALUES (2,70)");}catch(const std::runtime_error&){rejected=true;}
        assert(rejected&&!db.in_transaction()&&db.execute("SELECT value FROM c").rows[0][0]==50);
        rejected=false;try{T invalid(mode,0);}catch(const std::invalid_argument&){rejected=true;}assert(rejected);
    }
}
int main(){check<Database>();std::cout<<"global catalog admission and rebuild budget passed\n";}
