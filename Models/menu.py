from dataclasses import dataclass,field


@dataclass(slots=True)
class Food:
    name:str
    farsi_name:str
    price:int
    count:int=field(default=1)
    prep_count:int=field(default=3) # prepration of every 3 food takes prep_minutes
    prep_minutes:int=field(default=10)
    total_minutes:int=field(default=10,init=False)

    def post_init(self):
        self.total_minutes = int(self.count/self.prep_count) * self.prep_minutes
        if self.count%self.prep_count:
            self.total_minutes+=self.prep_minutes
        return self.total_minutes
    



