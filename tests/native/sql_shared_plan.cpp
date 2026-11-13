#include "../../native/relational/shared_plan.hpp"
#include <cassert>
#include <stdexcept>
using namespace refpot::foundation;
int main(){
 Definition a; a.name="a"; a.op="source"; a.width=2;
 Definition b=a; b.name="b";
 Definition f; f.name="f"; f.op="filter"; f.input="a"; f.column=0; f.cmp="gt"; f.value=0;
 Definition g=f; g.name="g";
 auto p=refpot::relational::compile_shared_plan({a,b,f,g},{"g"});
 assert(p.logical_definitions.size()==4 && p.physical_definitions.size()==3);
 assert(p.logical_to_physical.at("f")==p.logical_to_physical.at("g"));
 Definition j; j.name="j"; j.op="join"; j.left="a"; j.right="b"; j.left_key=0; j.right_key=0;
 Definition j2=j; j2.name="j2";
 auto q=refpot::relational::compile_shared_plan({a,b,j,j2},{});
 assert(q.logical_to_physical.at("j")==q.logical_to_physical.at("j2"));
 // Ordered join columns are semantic: swapping inputs changes output tuples.
 Definition reversed=j; reversed.name="reversed"; reversed.left="b"; reversed.right="a";
 auto ordered=refpot::relational::compile_shared_plan({a,b,j,reversed},{});
 assert(ordered.logical_to_physical.at("j")!=ordered.logical_to_physical.at("reversed"));
 assert(ordered.physical_definitions.back().left=="b");
 // Binary dependencies must be canonicalized for anti and union as well.
 Definition anti=j; anti.name="anti"; anti.op="anti"; anti.left="g";
 Definition anti2=anti; anti2.name="anti2"; anti2.left="f";
 auto binary=refpot::relational::compile_shared_plan({a,b,f,g,anti,anti2},{});
 assert(binary.logical_to_physical.at("anti")==binary.logical_to_physical.at("anti2"));
 Definition bad=f; bad.name="bad"; bad.right_column=9;
 bool threw=false; try { (void)refpot::relational::compile_shared_plan({a,b,bad},{}); } catch(const std::exception&) {threw=true;} assert(threw);
}
