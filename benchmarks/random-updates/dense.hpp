#include <unordered_map>
class DenseRows {
 using Entry=std::pair<int64_t,Row>;
 std::vector<Entry> values;
 std::unordered_map<int64_t,size_t> fallback;
 bool affine=true;
 __int128 step=0;
public:
 using iterator=std::vector<Entry>::iterator;
 using const_iterator=std::vector<Entry>::const_iterator;
 iterator begin(){return values.begin();}iterator end(){return values.end();}
 const_iterator begin()const{return values.begin();}const_iterator end()const{return values.end();}
 std::pair<iterator,bool> emplace(int64_t key,const Row&r){
  if(count(key))return {values.begin()+index(key),false};
  need(values.empty()||key>values.back().first,"sorted existing-key load");
  need(key==r.key,"row key identity");
  if(values.size()==1)step=(__int128)key-values.front().first;
  if(affine&&values.size()>1&&(__int128)key!=(__int128)values.front().first+step*values.size()){
   affine=false;fallback.reserve(values.size()*2+1);for(size_t i=0;i<values.size();i++)fallback.emplace(values[i].first,i);
  }
  if(!affine)fallback.emplace(key,values.size());
  values.emplace_back(key,r);return {values.end()-1,true};
 }
 bool locate(int64_t key,size_t& i)const noexcept{
  if(values.empty())return false;
  if(!affine){auto it=fallback.find(key);if(it==fallback.end())return false;i=it->second;return true;}
  if(values.size()==1){i=0;return values.front().first==key;}
  __int128 delta=(__int128)key-values.front().first;
  if(delta<0||step<=0||delta%step!=0)return false;
  __int128 quotient=delta/step;if(quotient>=(__int128)values.size())return false;
  i=(size_t)quotient;return values[i].first==key;
 }
 size_t index(int64_t key)const{size_t i;if(!locate(key,i))throw std::out_of_range("missing key");return i;}
 size_t count(int64_t key)const noexcept{size_t i;return locate(key,i)?1:0;}
 iterator find(int64_t key)noexcept{size_t i;return locate(key,i)?values.begin()+i:values.end();}
 const_iterator find(int64_t key)const noexcept{size_t i;return locate(key,i)?values.begin()+i:values.end();}
 Row& at(int64_t key){return values.at(index(key)).second;}
 const Row& at(int64_t key)const{return values.at(index(key)).second;}
 bool operator==(const DenseRows&o)const{return values==o.values;}
};
